"""Task 5 local read-only diagnostics, monitoring and incident correlation."""
import ipaddress
import json
import os
import platform
import shutil
import socket
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import (AuditEvent, BackupJob, DeviceHealthCheck, MonitoringEvent,
                        NetworkCheck, Ticket, User, utc_now)
from app.services.helpdesk_service import SLA_HOURS, ticket_history, log_event


def _allowed_items(name: str, default: str) -> set[str]:
    return {item.strip().lower() for item in os.getenv(name, default).split(',') if item.strip()}


def _authorise(kind: str, target: str, port: int | None) -> None:
    if kind == 'IPConfig':
        if target.lower() != 'localhost' or port is not None:
            raise HTTPException(422, 'IP configuration is only available for this device')
        return
    allowed = _allowed_items('OPS_DNS_TARGETS', 'localhost') if kind == 'DNS' else _allowed_items('OPS_TCP_TARGETS', 'localhost:8000')
    if (target.lower() if kind == 'DNS' else f'{target.lower()}:{port}') not in allowed:
        raise HTTPException(403, 'Target not in the explicitly approved diagnostic allowlist')
    if kind == 'DNS' and port is not None or kind == 'TCP' and port is None:
        raise HTTPException(422, 'TCP requires a port, DNS must not specify a port')
    if target.lower() not in {'localhost','127.0.0.1','::1'} and os.getenv('OPS_LAB_TARGETS_ENABLED','NO').upper() != 'YES':
        raise HTTPException(403, 'Nonlocal lab checks require OPS_LAB_TARGETS_ENABLED=YES')


def _permitted_ip(addr: str, target: str) -> bool:
    value = ipaddress.ip_address(addr.split('%')[0])
    if target.lower() in {'localhost','127.0.0.1','::1'}:
        return value.is_loopback
    return (value.is_private and not value.is_multicast and not value.is_link_local
            and not value.is_unspecified)  # public IP never allowed even with a DNS allowlist


def _resolve(target: str, port: int | None = None):
    addresses = socket.getaddrinfo(target, port, type=socket.SOCK_STREAM)
    allowed = [item for item in addresses if _permitted_ip(item[4][0], target)]
    if not allowed or len(allowed) != len(addresses):
        raise ValueError('Resolved target has unapproved/public addresses')
    return allowed


def _ip_config() -> dict:
    if platform.system() != 'Windows':
        return {'device': socket.gethostname(), 'os': platform.platform(),
                'note': 'Windows IP configuration requires Windows; use the isolated test fixture on other systems',
                'ipv4': [], 'gateway': None, 'dns_servers': []}
    # Fixed commands with no shell or user interpolation; only read local NIC configuration.
    script = ('Get-NetIPConfiguration | Select-Object InterfaceAlias,IPv4Address,IPv4DefaultGateway,DNSServer '
              '| ConvertTo-Json -Depth 6 -Compress')
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                            capture_output=True, text=True, timeout=12, check=True)
    return {'device': socket.gethostname(), 'interfaces': json.loads(result.stdout)}


def _check(kind: str, target: str, port: int | None) -> tuple[str, dict]:
    if kind == 'IPConfig':
        details = _ip_config()
        return ('Pass' if platform.system() == 'Windows' else 'Unavailable', details)
    addresses = _resolve(target, port)
    resolved = sorted({item[4][0] for item in addresses})
    if kind == 'DNS':
        return 'Pass', {'addresses': resolved}
    # Single TCP connect only: no port iteration, scan or arbitrary host resolution.
    errors = []
    for family, kind_sock, proto, _, sockaddr in addresses:
        try:
            with socket.socket(family, kind_sock, proto) as sock:
                sock.settimeout(1.5)
                sock.connect(sockaddr)
            return 'Pass', {'remote_address': sockaddr[0], 'port': port}
        except (OSError, TimeoutError) as exc:
            errors.append(type(exc).__name__)
    return 'Fail', {'addresses': resolved, 'port': port, 'errors': errors}


def _open_incident(db: Session, actor: User, *, title: str, details: str,
                   category: str = 'Network', priority: str = 'High', existing_id: int | None = None) -> Ticket:
    if existing_id:
        ticket = db.get(Ticket, existing_id)
        if ticket and ticket.status not in {'Resolved', 'Closed'}:
            return ticket
    ticket = Ticket(employee_id=actor.id, title=title[:160], description=details[:3000],
                    category=category, priority=priority, status='Open',
                    sla_due_at=utc_now()+timedelta(hours=SLA_HOURS[priority]))
    db.add(ticket)
    db.flush()
    ticket_history(db, ticket, actor, 'Created', note='Automatically generated from Task 5 monitoring')
    log_event(db, 'TICKET_CREATED', actor, ticket_id=ticket.id, source='Task5Monitoring')
    return ticket


def _event(db: Session, actor: User | None, kind: str, severity: str, reference: str, message: str,
           ticket_id: int | None = None):
    db.add(MonitoringEvent(event_type=kind, severity=severity, source_reference=reference[:100],
                           message=message[:1000], ticket_id=ticket_id,
                           actor_user_id=actor.id if actor else None))


def run_network_check(db: Session, actor: User, kind: str, target: str, port: int | None) -> NetworkCheck:
    _authorise(kind, target, port)
    start = time.perf_counter()
    try:
        result, details = _check(kind, target, port)
    except (OSError, ValueError, TimeoutError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        result, details = 'Fail', {'error': type(exc).__name__, 'message': str(exc)[:200]}
    elapsed = round((time.perf_counter()-start)*1000, 2)
    previous = db.scalars(select(NetworkCheck).where(NetworkCheck.check_type == kind,
        NetworkCheck.target == target, NetworkCheck.port == port, NetworkCheck.result == 'Fail')
        .order_by(NetworkCheck.id.desc()).limit(1)).first()
    ticket = None
    if result == 'Fail':
        ticket = _open_incident(db, actor, title=f'{kind} diagnostic failed: {target[:80]}',
                  details=f'{kind} target {target}:{port or ""} failed. {json.dumps(details)[:500]}',
                  existing_id=previous.ticket_id if previous else None)
    record = NetworkCheck(check_type=kind, target=target, port=port, result=result,
                          elapsed_ms=elapsed, details_json=json.dumps(details, default=str),
                          actor_user_id=actor.id, ticket_id=ticket.id if ticket else None)
    db.add(record); db.flush()
    _event(db, actor, 'NetworkCheck', 'Critical' if result == 'Fail' else 'Info',
           str(record.id), f'{kind} {target}: {result}', record.ticket_id)
    log_event(db, 'NETWORK_CHECK', actor, check_id=record.id, result=result)
    db.commit(); db.refresh(record)
    return record


def _windows_health() -> dict:
    script = ("$ErrorActionPreference='Stop'; "
              "$mp=$null; try {$mp=Get-MpComputerStatus -ErrorAction Stop} catch {}; "
              "$os=Get-CimInstance Win32_OperatingSystem -ErrorAction Stop; "
              "$av='Unavailable'; $rt='Unavailable'; $age=$null; "
              "if($null -ne $mp){ "
              "if($mp.AntivirusEnabled){$av='Enabled'}else{$av='Disabled'}; "
              "if($mp.RealTimeProtectionEnabled){$rt='Enabled'}else{$rt='Disabled'}; "
              "if($mp.AntivirusSignatureLastUpdated){$age=[int]((Get-Date)-$mp.AntivirusSignatureLastUpdated).TotalDays} }; "
              "[pscustomobject]@{device=$env:COMPUTERNAME;os=$os.Caption;antivirus=$av;"
              "realtime=$rt;signature_age=$age} | ConvertTo-Json -Compress")
    proc = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                          capture_output=True, text=True, timeout=15, check=True)
    return json.loads(proc.stdout)


def read_health() -> dict:
    disk = shutil.disk_usage(Path(__file__).resolve().parents[2])
    mode = os.getenv('OPS_HEALTH_MODE','mock').lower()
    if mode == 'windows':
        if platform.system() != 'Windows':
            details = {'device': socket.gethostname(), 'os': platform.platform(), 'antivirus':'Unavailable',
                       'realtime':'Unavailable', 'signature_age': None}
        else:
            try:
                details = _windows_health()
            except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
                details = {'device': socket.gethostname(), 'os': platform.platform(), 'antivirus':'Unavailable',
                           'realtime':'Unavailable', 'signature_age':None, 'note':type(exc).__name__}
    elif mode == 'mock':
        details = {'device': 'NORTHSTAR-WIN11-LAB', 'os': 'Windows 11 Pro (fictional)',
                   'antivirus': 'Enabled', 'realtime': 'Enabled', 'signature_age': 1, 'mock': True}
    else:
        raise HTTPException(500, 'OPS_HEALTH_MODE must be mock or windows')
    details['disk_total_bytes'] = disk.total
    details['disk_free_bytes'] = disk.free
    if details['antivirus'] == 'Disabled' or details['realtime'] == 'Disabled' or (details['signature_age'] or 0)>7 or disk.free/disk.total<0.1:
        details['status'] = 'Warning'
    elif details['antivirus'] == 'Unavailable':
        details['status'] = 'Unavailable'
    else:
        details['status'] = 'Healthy'
    return details


def save_health(db: Session, actor: User) -> DeviceHealthCheck:
    details = read_health()
    previous = db.scalars(select(DeviceHealthCheck).where(DeviceHealthCheck.hostname == details['device'],
               DeviceHealthCheck.status == 'Warning').order_by(DeviceHealthCheck.id.desc()).limit(1)).first()
    ticket = None
    if details['status'] == 'Warning':
        ticket = _open_incident(db, actor, title=f'Device health warning: {details["device"]}',
                 details='Read-only health checks reported an AV or disk threshold warning.', category='Software',
                 existing_id=previous.ticket_id if previous else None)
    record = DeviceHealthCheck(hostname=details['device'], os_description=details['os'],
              antivirus_status=details['antivirus'], realtime_protection=details['realtime'],
              definitions_age_days=details['signature_age'], disk_total_bytes=details['disk_total_bytes'],
              disk_free_bytes=details['disk_free_bytes'], status=details['status'],
              details_json=json.dumps(details), actor_user_id=actor.id,
              ticket_id=ticket.id if ticket else None)
    db.add(record); db.flush()
    _event(db, actor, 'DeviceHealth', 'Warning' if record.status != 'Healthy' else 'Info',
           str(record.id), f'{record.hostname}: {record.status}', record.ticket_id)
    log_event(db, 'DEVICE_HEALTH', actor, health_id=record.id, status=record.status)
    db.commit(); db.refresh(record)
    return record
