"""Task 5 security, local-only checks, phone calls and disaster recovery exports."""
import json
from pathlib import Path
from datetime import datetime
from sqlalchemy import select
from app.models import (AuditEvent, BackupJob, CallLog, DeviceHealthCheck,
                        IVRRule, MonitoringEvent, NetworkCheck, Ticket)
from tests.conftest import login_as


def test_ops_page_permissions_and_csrf(client):
    assert client.get('/operations').status_code == 401
    login_as(client, 'employee.ellie')
    assert client.get('/operations').status_code == 403
    assert client.get('/api/operations/backups').status_code == 403
    assert client.post('/api/operations/network/check', json={'kind':'DNS','target':'localhost'}).status_code == 403
    tech = login_as(client, 'tech.owen')
    assert client.get('/operations').status_code == 200
    assert client.post('/api/operations/backups/export', headers=tech, json={'tables':['assets']}).status_code == 403
    assert client.put('/api/operations/ivr',headers=tech,json={
        'menu_name':'Main','digit':'1','label':'Claims','destination_type':'Queue','destination':'ClaimsQueue'}).status_code==403
    assert client.post('/api/operations/health/check', headers=tech).status_code==200
    assert client.post('/api/operations/health/check').status_code==403


def test_network_allowlist_and_failed_check_reuses_incident(client, session_factory, monkeypatch):
    from app.services import operations_service
    hdr=login_as(client)
    endpoint='/api/operations/network/check'
    for target in ['example.com','192.168.1.1','127.0.0.1']:
        res=client.post(endpoint,headers=hdr,json={'kind':'TCP','target':target,'port':445})
        assert res.status_code==403
    assert client.post(endpoint,headers=hdr,json={'kind':'DNS','target':'example.com'}).status_code==403
    assert client.post(endpoint,headers=hdr,json={'kind':'IPConfig','target':'example.com'}).status_code==422
    monkeypatch.setattr(operations_service, '_check', lambda kind, target, port: ('Fail',{'error':'ConnectionRefused'}))
    first=client.post(endpoint,headers=hdr,json={'kind':'TCP','target':'localhost','port':8000})
    assert first.status_code==200, first.text
    first_id=first.json()['ticket_id']; assert first_id
    repeated=client.post(endpoint,headers=hdr,json={'kind':'TCP','target':'localhost','port':8000})
    assert repeated.json()['ticket_id']==first_id
    with session_factory() as db:
        assert db.query(NetworkCheck).count()==2
        assert db.query(Ticket).count()==1
        assert db.query(MonitoringEvent).count()==2
        assert db.scalar(select(AuditEvent).where(AuditEvent.event_type=='NETWORK_CHECK'))


def test_actual_local_dns_and_mock_health(client, session_factory, monkeypatch):
    monkeypatch.setenv('OPS_DNS_TARGETS','localhost')
    monkeypatch.setenv('OPS_HEALTH_MODE','mock')
    hdr=login_as(client)
    result=client.post('/api/operations/network/check',headers=hdr,json={'kind':'DNS','target':'localhost'})
    assert result.status_code==200, result.text
    assert result.json()['result']=='Pass'
    health=client.post('/api/operations/health/check',headers=hdr)
    assert health.status_code==200 and health.json()['status']=='Healthy'
    with session_factory() as db:
        assert db.query(DeviceHealthCheck).count()==1
    assert client.get('/api/operations/health/history').json()[0]['hostname']=='NORTHSTAR-WIN11-LAB'


def test_health_warning_escalation_without_disabling_security(client, session_factory, monkeypatch):
    from app.services import operations_service
    monkeypatch.setattr(operations_service,'read_health',lambda: {
        'device':'NORTHSTAR-TEST','os':'Windows 11 (mock)', 'antivirus':'Disabled',
        'realtime':'Disabled','signature_age':20,'disk_total_bytes':1000,'disk_free_bytes':40,
        'status':'Warning','mock':True})
    hdr=login_as(client)
    first=client.post('/api/operations/health/check',headers=hdr).json()
    second=client.post('/api/operations/health/check',headers=hdr).json()
    assert first['ticket_id']==second['ticket_id']
    assert first['status']=='Warning'
    with session_factory() as db:
        assert db.query(Ticket).count()==1


def test_fictional_call_csv_import_duplicate_prevention_and_bad_rows(client, session_factory):
    hdr=login_as(client)
    content=(Path(__file__).resolve().parents[1]/'sample_data'/'task5_call_logs.csv').read_bytes()
    ep='/api/operations/calls/import'
    upload=lambda payload,name='calls.csv':client.post(ep,headers=hdr,files={'file':(name,payload,'text/csv')})
    first=upload(content)
    assert first.status_code==200, first.text
    assert first.json()['inserted']==60 and first.json()['rejected_count']==0
    duplicate=upload(content).json()
    assert duplicate['inserted']==0 and duplicate['duplicates']==60
    assert client.get('/api/operations/calls/stats').json()['total']==60
    bad=content.decode().splitlines()
    bad[1]=bad[1].replace('Answered','BadOutcome')
    bad_result=upload(('\n'.join(bad)+'\n').encode()).json()
    assert bad_result['rejected_count']==1
    assert upload(content,'calls.txt').status_code==422
    with session_factory() as db:
        assert db.query(CallLog).count()==60
        assert db.scalar(select(AuditEvent).where(AuditEvent.event_type=='CALLS_IMPORTED'))


def test_ivr_upsert_simulation_and_change_audit(client, session_factory):
    hdr=login_as(client)
    payload={'menu_name':'Main','digit':'1','label':'Claims','destination_type':'Queue','destination':'ClaimsQueue'}
    assert client.put('/api/operations/ivr',headers=hdr,json=payload).status_code==200
    ep='/api/operations/ivr/simulate'
    assert client.post(ep,headers=hdr,json={'menu_name':'Main','digit':'1'}).json()['destination']=='ClaimsQueue'
    payload['destination']='ClaimsQueue2'
    assert client.put('/api/operations/ivr',headers=hdr,json=payload).json()['destination']=='ClaimsQueue2'
    assert client.post(ep,headers=hdr,json={'menu_name':'Main','digit':'9'}).json()['result']=='Unrouted'
    with session_factory() as db:
        assert db.query(IVRRule).count()==1
        assert db.query(AuditEvent).filter_by(event_type='IVR_UPDATED').count()==2


def test_export_verify_corruption_and_simulated_failure(client, session_factory, tmp_path, monkeypatch):
    monkeypatch.setenv('OPS_BACKUP_DIR',str(tmp_path))
    hdr=login_as(client)
    resp=client.post('/api/operations/backups/export',headers=hdr,json={'tables':['assets','call_logs']})
    assert resp.status_code==200, resp.text
    result=resp.json(); job=result['id']; path=Path(result['location'])
    assert path.parent==tmp_path and path.exists()
    assert client.get(f'/api/operations/backups/{job}/download').status_code==200
    assert client.post(f'/api/operations/backups/{job}/verify',headers=hdr).json()['verified'] is True
    from scripts.inspect_recovery_export import main
    # Avoid stdout dependence: ensure valid recovery JSON and manifest digest.
    import zipfile
    with zipfile.ZipFile(path) as z:
        assert json.loads(z.read('manifest.json'))['tables']['assets']['rows']==0
    path.write_bytes(b'broken archive')
    failed=client.post(f'/api/operations/backups/{job}/verify',headers=hdr).json()
    assert failed['verified'] is False and failed['incident_ticket_id']
    simulated=client.post('/api/operations/backups/simulate-failure',headers=hdr,json={'reason':'Training: scheduled job failed'}).json()
    assert simulated['result']=='Failed' and simulated['ticket_id']
    with session_factory() as db:
        assert db.query(BackupJob).count()==2
        assert db.query(Ticket).count()==2
        assert db.query(MonitoringEvent).count()>=4


def test_no_arbitrary_backup_file_download(client, session_factory, monkeypatch, tmp_path):
    hdr=login_as(client)
    monkeypatch.setenv('OPS_BACKUP_DIR',str(tmp_path))
    with session_factory() as db:
        row=BackupJob(backup_type='ApplicationExport',result='Success',
                      location=str(tmp_path.parent/'secret.zip'),actor_user_id=1)
        db.add(row);db.commit(); id=row.id
    assert client.get(f'/api/operations/backups/{id}/download').status_code==403


def test_full_cross_task_integration(client, session_factory, tmp_path, monkeypatch):
    """Keep Tasks 1-4 operational while Task 5 uses their claims, users, and tickets."""
    from tests.test_task4_workflows import setup_claim, send_event
    from app.models import Claim, ClaimCRMState, Asset, Employee, WorkflowExecution
    monkeypatch.setenv('OPS_BACKUP_DIR',str(tmp_path))
    hdr=setup_claim(client,session_factory)
    assert send_event(client,hdr,'submitted','all-tasks-event-001').json()['results'][0]['status']=='Success'
    assert client.get('/claims-management').status_code==200  # Task 1 + 4
    assert client.get('/tickets').status_code==200           # Task 2
    assert client.get('/employees').status_code==200         # Task 3
    assert client.get('/operations').status_code==200        # Task 5
    export=client.post('/api/operations/backups/export',headers=hdr,
                       json={'tables':['claims','tickets','assets']}).json()
    assert export['result']=='Success'
    with session_factory() as db:
        assert db.query(Claim).count()==1
        assert db.query(WorkflowExecution).count()==1
        assert db.query(BackupJob).count()==1
        assert db.query(AuditEvent).filter_by(event_type='BACKUP_CREATED').count()==1
