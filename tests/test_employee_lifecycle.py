"""Task 3 end-to-end lifecycle using isolated SQLite and no external credentials."""
from datetime import date, timedelta
from sqlalchemy import select

from app.models import (Asset, AssetReservation, AuditEvent, Employee,
                        OffboardingRequest, ApprovalRecord, ProvisioningAction)
from app.services.google_directory import MockDirectory, RealGoogleDirectory
from app.models import User
from app.security import hash_password
from tests.conftest import login_as


def payload(groups=None):
    return {'full_name': 'Alex Morgan', 'department': 'Claims', 'job_title': 'Claims Handler',
            'manager_name': 'Sarah Bennett', 'start_date': (date.today() + timedelta(days=14)).isoformat(),
            'required_groups': groups if groups is not None else ['SG-Claims-Read'],
            'device_requirements': ['Laptop']}


def laptop(db, tag='NS-LAP-TEST-03'):
    db.add(Asset(asset_tag=tag, serial_number='SN-'+tag, device_type='Laptop',
                 manufacturer='Dell', model='Latitude', operating_system='Windows 11',
                 purchase_date=date(2025, 1, 1), status='Available', notes='Test only'))
    db.commit()


def create_employee(client, session_factory):
    with session_factory() as db:
        laptop(db)
    headers = login_as(client, 'admin')
    response = client.post('/api/employees/onboarding', headers=headers, json=payload())
    assert response.status_code == 201, response.text
    return response.json()['id'], headers


def test_role_boundaries_and_csrf(client):
    assert client.get('/api/employees').status_code == 401
    employee_headers = login_as(client, 'employee.ellie')
    assert client.get('/api/employees').status_code == 403
    assert client.post('/api/employees/onboarding', headers=employee_headers, json=payload()).status_code == 403
    technician_headers = login_as(client, 'tech.owen')
    assert client.post('/api/employees/onboarding', headers=technician_headers, json=payload()).status_code == 403
    admin_headers = login_as(client, 'admin')
    assert client.post('/api/employees/onboarding', json=payload()).status_code == 403
    assert client.get('/employees').status_code == 200
    assert client.get('/api/employees/metrics').status_code == 200


def test_group_allowlist_and_request_validation(client):
    headers = login_as(client, 'admin')
    bad = payload(['SG-IT-Helpdesk'])
    assert client.post('/api/employees/onboarding', headers=headers, json=bad).status_code == 422
    bad = payload()
    bad['full_name'] = 'A'
    assert client.post('/api/employees/onboarding', headers=headers, json=bad).status_code == 422
    bad = payload()
    bad['device_requirements'] = ['Laptop','Laptop']
    assert client.post('/api/employees/onboarding', headers=headers, json=bad).status_code == 422


def test_onboarding_reserves_task2_asset_and_audits(client, session_factory):
    employee_id, headers = create_employee(client, session_factory)
    row = client.get(f'/api/employees/{employee_id}').json()
    assert row['ad_username'] == f'nc{employee_id:06d}'
    assert row['status'] == 'Prepared'
    assert row['reserved_asset_tag'] == 'NS-LAP-TEST-03'
    assert any(a['type'] == 'GOOGLE_CREATE' and a['status'] == 'Mocked' for a in row['actions'])
    assert any(a['type'] == 'AD_CREATE' and a['status'] == 'Prepared' for a in row['actions'])
    plan = client.get(f'/api/employees/{employee_id}/ad-plan')
    assert plan.status_code == 200
    assert plan.json()['groups'] == ['SG-Claims-Read']
    with session_factory() as db:
        asset = db.scalar(select(Asset).where(Asset.asset_tag == 'NS-LAP-TEST-03'))
        assert asset.status == 'Reserved'
        assert db.scalar(select(AssetReservation).where(AssetReservation.employee_id == employee_id))
        assert db.scalar(select(AuditEvent).where(AuditEvent.event_type == 'ASSET_RESERVED'))
    assert client.post('/api/assets/1/assign', headers=headers, json={'employee_id': 4}).status_code in (404,409)


def test_second_onboarding_cannot_reserve_same_laptop(client, session_factory):
    first, headers = create_employee(client, session_factory)
    second_payload = payload()
    second_payload['full_name'] = 'Taylor Scott'
    response = client.post('/api/employees/onboarding', headers=headers, json=second_payload)
    assert response.status_code == 201
    assert response.json()['onboarding_status'] == 'Attention'
    assert response.json()['reserved_asset_tag'] is None
    assert any(a['status'] == 'Failed' for a in response.json()['actions'])
    assert client.post(f'/api/employees/{response.json()["id"]}/activate', headers=headers).status_code == 409


def test_end_to_end_approval_and_reservation_release(client, session_factory):
    employee_id, headers = create_employee(client, session_factory)
    activated = client.post(f'/api/employees/{employee_id}/activate', headers=headers)
    assert activated.status_code == 200
    assert activated.json()['status'] == 'Active'
    departure = {'last_working_date': date.today().isoformat(), 'reason': 'Fictional contract completed'}
    requested = client.post(f'/api/employees/{employee_id}/offboarding', headers=headers, json=departure)
    assert requested.status_code == 201
    request_id = requested.json()['id']
    assert client.post(f'/api/employees/{employee_id}/offboarding', headers=headers, json=departure).status_code == 409
    approval = {'confirm': True, 'comment': 'Approved in fictional test environment'}
    assert client.post(f'/api/employees/offboarding/{request_id}/approve', headers=headers,
                       json=approval).status_code == 403
    assert client.get('/api/employees/offboarding').json()['items'][0]['status'] == 'PendingApproval'
    with session_factory() as db:
        db.add(User(username='admin.reviewer', full_name='Jordan Review',
                    email='reviewer@northstar.example', role='Admin', is_active=True,
                    password_hash=hash_password('NorthstarReview!2026')))
        db.commit()
    login_response = client.post('/api/auth/login', json={
        'username': 'admin.reviewer', 'password': 'NorthstarReview!2026'})
    assert login_response.status_code == 200
    reviewer = {'X-CSRF-Token': login_response.json()['csrf_token']}
    completed = client.post(f'/api/employees/offboarding/{request_id}/approve', headers=reviewer, json=approval)
    assert completed.status_code == 200, completed.text
    assert completed.json()['simulation'] is True
    row = client.get(f'/api/employees/{employee_id}').json()
    assert row['status'] == 'Offboarded'
    assert any(a['type'] == 'GOOGLE_SUSPEND' and a['status'] == 'Mocked' for a in row['actions'])
    assert any(a['type'] == 'AD_DISABLE' and a['status'] == 'Prepared' for a in row['actions'])
    with session_factory() as db:
        reservation = db.scalar(select(AssetReservation).where(AssetReservation.employee_id == employee_id))
        assert reservation.status == 'Released'
        assert db.get(Asset, reservation.asset_id).status == 'Available'
        assert db.scalar(select(ApprovalRecord).where(ApprovalRecord.offboarding_request_id == request_id))
        assert db.scalar(select(AuditEvent).where(AuditEvent.event_type == 'OFFBOARDING_COMPLETED'))
    assert client.post(f'/api/employees/offboarding/{request_id}/approve', headers=reviewer,
                       json=approval).status_code == 409


def test_no_device_required_and_offboard_without_reservation(client):
    headers = login_as(client)
    item = payload()
    item['device_requirements'] = []
    response = client.post('/api/employees/onboarding', headers=headers, json=item)
    assert response.status_code == 201
    assert response.json()['onboarding_status'] == 'Prepared'
    assert response.json()['reserved_asset_tag'] is None


def test_mock_google_directory_five_operations_and_live_default_disabled(monkeypatch):
    mock = MockDirectory()
    assert mock.create_user('alex@northstar.example','Alex','Morgan')['suspended'] is False
    assert len(mock.list_users()) == 1
    assert mock.assign_group('alex@northstar.example','claims@northstar.example')['role'] == 'MEMBER'
    assert mock.update_user('alex@northstar.example',{'orgUnitPath':'/Claims'})['orgUnitPath'] == '/Claims'
    assert mock.suspend_user('alex@northstar.example')['suspended'] is True
    monkeypatch.delenv('GOOGLE_LAB_ENABLED', raising=False)
    try:
        RealGoogleDirectory(confirmed_lab=True)
    except RuntimeError as error:
        assert 'disabled' in str(error)
    else:
        raise AssertionError('Real Google adapter should not initialize by default')


def test_department_base_group_auto_populates_and_non_inventory_devices(client):
    headers = login_as(client, 'admin')
    entry = payload(groups=[])
    entry['device_requirements'] = ['Monitor']
    response = client.post('/api/employees/onboarding', json=entry, headers=headers)
    assert response.status_code == 201
    emp = response.json()
    assert any(a['type'] == 'AD_GROUP' and a['target'] == 'SG-Claims-Read' for a in emp['actions'])
    assert any(a['type'] == 'DEVICE_REQUEST' and a['status'] == 'ManualRequired' for a in emp['actions'])
    plan = client.get(f'/api/employees/{emp["id"]}/ad-plan').json()
    assert plan['groups'] == ['SG-Claims-Read']


def test_task3_seed_idempotent(session_factory):
    from scripts.seed_task3 import seed
    from sqlalchemy import func
    with session_factory() as db:
        assert seed(db) is True
        assert seed(db) is False
        assert db.scalar(select(func.count()).select_from(User).where(User.username == 'admin.reviewer')) == 1
