"""Complete practical helpdesk walkthrough: laptop assignment through ticket closure."""
from sqlalchemy import func, select
from app.models import Asset, AuditEvent, Ticket, TicketHistory
from tests.conftest import login_as
from tests.test_assets import laptop


def test_laptop_fault_reported_assigned_investigated_resolved_closed(client, session_factory):
    # IT prepares a real (fictional) laptop and assigns it to employee Ellie.
    tech_headers = login_as(client, 'tech.owen')
    asset = client.post('/api/assets', json=laptop(), headers=tech_headers).json()
    assigned_asset = client.post(f"/api/assets/{asset['id']}/assign",
        json={'employee_id':4}, headers=tech_headers)
    assert assigned_asset.status_code == 200

    # Ellie submits a hardware incident and selects only the device assigned to her.
    employee_headers = login_as(client, 'employee.ellie')
    ticket_data = {
        'title':'Laptop crashes on startup',
        'description':'The Latitude 5440 blue-screens at sign-in, blocking claims processing.',
        'category':'Hardware', 'priority':'High', 'affected_asset_id':asset['id'],
    }
    ticket_response = client.post('/api/tickets', json=ticket_data, headers=employee_headers)
    assert ticket_response.status_code == 201
    ticket = ticket_response.json()
    assert ticket['reference'].startswith('TKT-') and ticket['asset_tag'] == asset['asset_tag']

    # Admin triages and assigns Owen.
    admin_headers = login_as(client)
    route = f"/api/tickets/{ticket['id']}"
    assert client.post(route+'/assign', json={'technician_id':2}, headers=admin_headers).json()['status'] == 'Assigned'

    # Owen investigates, notes evidence, resolves with a concrete change record.
    tech_headers = login_as(client, 'tech.owen')
    assert client.patch(route, json={'status':'In Progress'}, headers=tech_headers).status_code == 200
    assert client.post(route+'/notes', json={
        'note':'Event Viewer shows outdated graphics driver; ran hardware diagnostics.'
    }, headers=tech_headers).status_code == 201
    fixed = client.patch(route, json={
        'status':'Resolved',
        'resolution_details':'Installed approved display driver, restarted three times, and verified claim access.'
    }, headers=tech_headers)
    assert fixed.status_code == 200 and fixed.json()['resolved_at']
    assert fixed.json()['sla_status'] == 'Met'

    # Admin closes and exports the report; ticket history is append-only.
    admin_headers = login_as(client)
    closed = client.patch(route, json={'status':'Closed'}, headers=admin_headers)
    assert closed.status_code == 200 and closed.json()['closed_at']
    assert len(closed.json()['history']) == 6
    assert client.get('/api/reports/tickets.xlsx').status_code == 200
    with session_factory() as db:
        assert db.get(Asset, asset['id']).assigned_employee_id == 4
        assert db.get(Ticket,ticket['id']).status == 'Closed'
        assert db.scalar(select(func.count()).select_from(TicketHistory).where(TicketHistory.ticket_id==ticket['id'])) == 6
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type=='TICKET_UPDATED')) == 3
