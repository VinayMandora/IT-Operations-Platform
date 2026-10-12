"""Admin-only selected-record recovery snapshots; encrypted storage recommended outside this demo.

Exports are written under a configured local directory and are NEVER automatically
restored into the source database. SQL Server full backup lives in a separate .sql script.
"""
import hashlib
import json
import os
import uuid
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import Asset, BackupJob, CallLog, Claim, Ticket, User, utc_now
from app.services.helpdesk_service import log_event
from app.services.operations_service import _event, _open_incident

TABLES = {'claims':Claim, 'tickets':Ticket, 'assets':Asset, 'call_logs':CallLog}
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def backup_folder() -> Path:
    folder = Path(os.getenv('OPS_BACKUP_DIR',str(PROJECT_ROOT / 'backups'))).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def safe_path(job: BackupJob) -> Path:
    # A saved DB location is never trusted as an arbitrary download path.
    folder = backup_folder()
    path = Path(job.location).resolve()
    if job.backup_type != 'ApplicationExport' or path.parent != folder or path.suffix != '.zip':
        raise HTTPException(403, 'Only managed application export archives may be downloaded')
    return path


def _encode(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def export_records(db: Session, actor: User, tables: list[str]) -> BackupJob:
    if not tables or len(set(tables)) != len(tables) or not set(tables).issubset(TABLES):
        raise HTTPException(422, 'Choose distinct approved application tables')
    folder = backup_folder()
    timestamp = utc_now().strftime('%Y%m%dT%H%M%S')
    path = folder / f'northstar-export-{timestamp}-{uuid.uuid4().hex[:12]}.zip'
    try:
        manifest = {'format':'NorthstarRecoverySnapshotV1', 'created_utc':utc_now().isoformat()+'Z',
                    'tables':{}, 'purpose':'offline isolated lab recovery only'}
        with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for table in tables:
                model = TABLES[table]
                names = [c.name for c in model.__table__.columns]
                count = db.scalar(select(func.count()).select_from(model)) or 0
                if count > 100000:
                    raise ValueError(f'{table} contains over 100000 rows; export deliberately refuses incomplete snapshots')
                records = [{name:getattr(row,name) for name in names}
                           for row in db.scalars(select(model).order_by(model.id))]
                payload = json.dumps(records, ensure_ascii=False, default=_encode, separators=(',',':')).encode('utf-8')
                filename = f'{table}.json'
                archive.writestr(filename, payload)
                manifest['tables'][table] = {'rows':len(records),'sha256':hashlib.sha256(payload).hexdigest()}
            archive.writestr('manifest.json', json.dumps(manifest, indent=2).encode('utf-8'))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        job = BackupJob(backup_type='ApplicationExport', result='Success', location=str(path),
                        file_size=path.stat().st_size, sha256=digest, verified_at=utc_now(),
                        actor_user_id=actor.id)
        db.add(job); db.flush()
        _event(db, actor, 'BackupExport', 'Info', str(job.id), f'Exported: {", ".join(tables)}')
        log_event(db, 'BACKUP_CREATED', actor, job_id=job.id, tables=tables)
        db.commit(); db.refresh(job)
        return job
    except Exception:
        path.unlink(missing_ok=True)
        db.rollback()
        raise


def verify_export(db: Session, actor: User, job: BackupJob) -> dict:
    path = safe_path(job)
    failure = None
    try:
        if not path.is_file() or path.stat().st_size != int(job.file_size or 0):
            raise ValueError('Backup archive missing or file size changed')
        if hashlib.sha256(path.read_bytes()).hexdigest() != job.sha256:
            raise ValueError('SHA-256 hash mismatch')
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError('ZIP checksum failure')
            manifest = json.loads(archive.read('manifest.json'))
            if manifest.get('format') != 'NorthstarRecoverySnapshotV1':
                raise ValueError('Unsupported snapshot version')
            for name, info in manifest['tables'].items():
                if name not in TABLES:
                    raise ValueError('Unexpected table in archive')
                payload = archive.read(name+'.json')
                if hashlib.sha256(payload).hexdigest() != info['sha256'] or len(json.loads(payload)) != info['rows']:
                    raise ValueError('Manifest integrity failure')
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        failure = str(exc)[:500]
    if failure:
        job.result = 'Failed'; job.failure_reason = failure
        ticket = _open_incident(db, actor, title='Application backup verification failed',
                               details=f'Backup #{job.id}: {failure}', category='Software',
                               existing_id=job.ticket_id)
        job.ticket_id = ticket.id
        _event(db, actor, 'BackupFailure', 'Critical', str(job.id), failure, ticket.id)
        log_event(db, 'BACKUP_FAILED', actor, backup_id=job.id, reason=failure)
    else:
        job.result = 'Success'; job.verified_at=utc_now(); job.failure_reason=None
        _event(db, actor, 'BackupVerified', 'Info', str(job.id), 'SHA-256 and manifest verified')
        log_event(db, 'BACKUP_VERIFIED', actor, backup_id=job.id)
    db.commit()
    return {'backup_id':job.id, 'verified':not bool(failure), 'failure_reason':failure,
            'incident_ticket_id':job.ticket_id}


def simulate_backup_failure(db: Session, actor: User, reason: str) -> BackupJob:
    # Intentionally never runs an actual backup command.
    ticket = _open_incident(db, actor, title='Simulated SQL Server backup failure',
                           details=f'Simulation only: {reason}', category='Software', priority='High')
    job = BackupJob(backup_type='Simulation', result='Failed',
                    location='SIMULATION — no backup file', failure_reason=reason,
                    actor_user_id=actor.id, ticket_id=ticket.id)
    db.add(job); db.flush()
    _event(db, actor, 'BackupFailure', 'Critical', str(job.id), reason, ticket.id)
    log_event(db, 'BACKUP_FAILED', actor, backup_id=job.id, simulated=True, ticket_id=ticket.id)
    db.commit(); db.refresh(job)
    return job
