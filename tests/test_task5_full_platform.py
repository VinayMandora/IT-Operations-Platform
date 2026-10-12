"""One continuous isolated end-to-end transaction sequence spanning all five real modules."""
from sqlalchemy import select
from app.models import (Asset, AssetReservation, AuditEvent, BackupJob, Claim,
                        Employee, MonitoringEvent, NetworkCheck, Ticket, WorkflowExecution)
from tests.conftest import login_as
from tests.test_employee_lifecycle import laptop, payload as onboarding_payload
from tests.test_helpdesk import payload as ticket_payload
from tests.test_task4_workflows import setup_claim, send_event


def test_all_five_tasks_share_one_database_and_audit(client, session_factory, tmp_path, monkeypatch):
    from app.services import operations_service
    monkeypatch.setenv('OPS_BACKUP_DIR',str(tmp_path))
    admin = setup_claim(client,session_factory)  # Task 1 import + Task 4 rule seed

    with session_factory() as db:
        laptop(db,'NS-LAP-FIVE-TASK')             # Task 2 asset
    created=client.post('/api/employees/onboarding',headers=admin,json=onboarding_payload())
    assert created.status_code==201,created.text  # Task 3 reserves Task 2 laptop
    assert created.json()['reserved_asset_tag']=='NS-LAP-FIVE-TASK'
    empid=created.json()['id']

    staff=login_as(client,'employee.ellie')
    ticket=client.post('/api/tickets',headers=staff,json=ticket_payload())
    assert ticket.status_code==201,ticket.text    # Task 2 employee helpdesk
    admin=login_as(client,'admin')
    processed=send_event(client,admin,'submitted','full-five-integrated-0001')
    assert processed.status_code==200
    assert processed.json()['results'][0]['status']=='Success'  # Task 4 workflow on Task 1 claim

    monkeypatch.setattr(operations_service, '_check',lambda *_:('Fail',{'error':'TrainingOffline'}))
    failed=client.post('/api/operations/network/check',headers=admin,json={
        'kind':'TCP','target':'localhost','port':8000})
    assert failed.status_code==200 and failed.json()['ticket_id']   # Task 5 -> Task 2
    backup=client.post('/api/operations/backups/export',headers=admin,
                       json={'tables':['claims','tickets','assets']})
    assert backup.status_code==200
    assert client.post(f'/api/operations/backups/{backup.json()["id"]}/verify',headers=admin).json()['verified']

    with session_factory() as db:
        assert db.query(Claim).count()==1
        assert db.get(Employee,empid).status=='Prepared'
        assert db.query(AssetReservation).count()==1
        assert db.query(WorkflowExecution).count()==1
        assert db.query(NetworkCheck).count()==1
        assert db.query(BackupJob).count()==1
        assert db.query(Ticket).count()==2  # original laptop fault + auto networking incident
        kinds=set(db.scalars(select(AuditEvent.event_type)).all())
        assert {'IMPORT_COMPLETED','TICKET_CREATED','ONBOARDING_PREPARED',
                'CLAIM_WORKFLOW','NETWORK_CHECK','BACKUP_CREATED','BACKUP_VERIFIED'}.issubset(kinds)
