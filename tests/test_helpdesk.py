"""API integration: RBAC, CSRF, ticket lifecycle, SLA and audit trail."""
from datetime import timedelta
from sqlalchemy import func, select
from app.models import AuditEvent, Ticket, TicketHistory, utc_now
from tests.conftest import login_as


def payload(asset=None):
    return {'title': 'Laptop blue screen after restart',
            'description': 'Device crashes with blue screen on startup, error code is displayed.',
            'category': 'Hardware', 'priority': 'High', 'affected_asset_id': asset}


def test_login_validation_and_csrf(client):
    assert client.get('/api/tickets').status_code == 401
    assert client.post('/api/auth/login', json={'username':'admin','password':'wrong'}).status_code == 401
    login_as(client, 'employee.ellie')
    assert client.post('/api/tickets', json=payload()).status_code == 403
    assert client.get('/api/auth/me').json()['role'] == 'Employee'


def test_employee_ownership_ticket_assignment_and_resolution(client, session_factory):
    employee_csrf = login_as(client, 'employee.ellie')
    response = client.post('/api/tickets', json=payload(), headers=employee_csrf)
    assert response.status_code == 201, response.text
    ticket = response.json()
    ticket_id = ticket['id']
    assert ticket['reference'] == f'TKT-{ticket_id:06d}'
    assert ticket['status'] == 'Open' and ticket['sla_status'] == 'On track'
    assert ticket['history'][0]['action'] == 'Created'
    assert client.get(f'/api/tickets/{ticket_id}').status_code == 200
    assert client.post(f'/api/tickets/{ticket_id}/notes', json={'note':'test'}, headers=employee_csrf).status_code == 403
    other_csrf = login_as(client, 'employee.jamie')
    assert client.get(f'/api/tickets/{ticket_id}').status_code == 404
    assert all(t['id'] != ticket_id for t in client.get('/api/tickets').json()['items'])
    assert client.post(f'/api/tickets/{ticket_id}/assign', json={'technician_id':2}, headers=other_csrf).status_code == 403
    tech_csrf = login_as(client, 'tech.owen')
    assert client.patch(f'/api/tickets/{ticket_id}', json={'status':'In Progress'}, headers=tech_csrf).status_code == 404
    assigned = client.post(f'/api/tickets/{ticket_id}/assign', json={'technician_id':2}, headers=tech_csrf)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()['status'] == 'Assigned'
    assert client.patch(f'/api/tickets/{ticket_id}', json={'status':'Resolved'}, headers=tech_csrf).status_code == 422  # resolution missing
    note = client.post(f'/api/tickets/{ticket_id}/notes', json={'note':'Checked event logs and blue screen stop code.'}, headers=tech_csrf)
    assert note.status_code == 201
    progress = client.patch(f'/api/tickets/{ticket_id}', json={'status':'In Progress'}, headers=tech_csrf)
    assert progress.status_code == 200
    resolved = client.patch(f'/api/tickets/{ticket_id}', json={
        'status':'Resolved','resolution_details':'Updated graphics driver and confirmed three successful restarts.'}, headers=tech_csrf)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()['resolved_at'] and resolved.json()['sla_status'] == 'Met'
    assert len(resolved.json()['history']) == 5
    admin_headers = login_as(client, 'admin')
    closed = client.patch(f'/api/tickets/{ticket_id}', json={'status':'Closed'}, headers=admin_headers)
    assert closed.status_code == 200
    assert closed.json()['closed_at'] is not None
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(TicketHistory)) >= 6
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == 'TICKET_CREATED')) == 1


def test_assignment_permission_and_ticket_validation(client):
    admin = login_as(client, 'admin')
    bad = client.post('/api/tickets', json={**payload(), 'priority':'Urgent'}, headers=admin)
    assert bad.status_code == 422
    ticket = client.post('/api/tickets', json=payload(), headers=admin).json()
    tech = login_as(client, 'tech.owen')
    assert client.post(f"/api/tickets/{ticket['id']}/assign", json={'technician_id':3}, headers=tech).status_code == 403
    assert client.post(f"/api/tickets/{ticket['id']}/assign", json={'technician_id':2}, headers=tech).status_code == 200
    other = login_as(client, 'tech.maya')
    assert client.post(f"/api/tickets/{ticket['id']}/assign", json={'technician_id':3}, headers=other).status_code == 409
    assert client.post(f"/api/tickets/{ticket['id']}/notes", json={'note':'not my ticket'}, headers=other).status_code == 404


def test_sla_overdue_logic(client, session_factory):
    admin = login_as(client)
    ticket_id = client.post('/api/tickets', json=payload(), headers=admin).json()['id']
    with session_factory() as db:
        ticket = db.get(Ticket,ticket_id)
        ticket.sla_due_at = utc_now() - timedelta(minutes=1)
        db.commit()
    assert client.get(f'/api/tickets/{ticket_id}').json()['sla_status'] == 'Overdue'
    assert 'Overdue SLA' in client.get('/').text


def test_admin_accounts_employee_cannot_create_users(client):
    body = {'username':'new.staff','full_name':'New Staff','email':'new.staff@northstar.example',
            'role':'Employee','password':'A-reasonably-long-2026-password'}
    emp = login_as(client,'employee.ellie')
    assert client.post('/api/users',json=body,headers=emp).status_code == 403
    admin = login_as(client)
    created = client.post('/api/users',json=body,headers=admin)
    assert created.status_code == 201, created.text
    assert 'password_hash' not in created.text
    assert client.post('/api/users',json=body,headers=admin).status_code == 409
    assert any(x['username']=='new.staff' for x in client.get('/api/users').json()['items'])


def test_admin_can_update_accounts_but_cannot_disable_self(client):
    admin=login_as(client)
    assert client.patch('/api/users/1',json={'is_active':False},headers=admin).status_code==409
    changed=client.patch('/api/users/5',json={'full_name':'Jamie Patricia Patel'},headers=admin)
    assert changed.status_code==200
    assert changed.json()['full_name']=='Jamie Patricia Patel'
    assert client.patch('/api/users/5',json={'is_active':False},headers=admin).status_code==200
    assert client.post('/api/auth/login',json={'username':'employee.jamie',
                    'password':'NorthstarStaff!2026'}).status_code==401
