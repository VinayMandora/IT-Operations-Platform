"""Ticket state machine, SLA computation, audit and serialization."""
import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import AuditEvent, Ticket, TicketHistory, User, utc_now

SLA_HOURS = {'Low': 72, 'Medium': 24, 'High': 8, 'Critical': 2}
TRANSITIONS = {
    'Open': {'Assigned'}, 'Assigned': {'In Progress','Resolved'},
    'In Progress': {'Resolved'}, 'Resolved': {'Closed','In Progress'},
    'Closed': set(),
}


def log_event(db: Session, event: str, actor: User, **details) -> None:
    db.add(AuditEvent(event_type=event, actor_user_id=actor.id,
                      details_json=json.dumps(details, ensure_ascii=False, default=str)))


def ticket_history(db: Session, ticket: Ticket, actor: User, action: str,
                   note: str = '', previous: str | None = None, new: str | None = None):
    db.add(TicketHistory(ticket_id=ticket.id, actor_user_id=actor.id, action=action,
                         previous_status=previous, new_status=new, note=note))


def allowed_ticket(user: User, ticket: Ticket, *, write: bool = False) -> bool:
    if user.role == 'Admin':
        return True
    if user.role == 'Employee':
        return not write and ticket.employee_id == user.id
    if user.role == 'Technician':
        return ticket.assigned_technician_id == user.id if write else (
            ticket.assigned_technician_id == user.id or ticket.employee_id == user.id)
    return False


def require_ticket(user: User, ticket: Ticket | None, *, write: bool = False) -> Ticket:
    # Do not reveal another employee's ticket existence.
    if not ticket or not allowed_ticket(user, ticket, write=write):
        raise HTTPException(404, 'Ticket not found')
    return ticket


def sla_status(ticket: Ticket) -> str:
    if ticket.resolved_at:
        return 'Met' if ticket.resolved_at <= ticket.sla_due_at else 'Breached'
    if ticket.status == 'Closed':
        return 'Closed'
    return 'Overdue' if utc_now() > ticket.sla_due_at else 'On track'


def ticket_dict(ticket: Ticket, *, with_history: bool = False) -> dict:
    value = {
        'id': ticket.id, 'reference': ticket.reference, 'title': ticket.title,
        'description': ticket.description, 'category': ticket.category,
        'priority': ticket.priority, 'status': ticket.status,
        'employee_id': ticket.employee_id, 'employee': ticket.employee.full_name,
        'assigned_technician_id': ticket.assigned_technician_id,
        'technician': ticket.technician.full_name if ticket.technician else None,
        'affected_asset_id': ticket.affected_asset_id,
        'asset_tag': ticket.asset.asset_tag if ticket.asset else None,
        'resolution_details': ticket.resolution_details,
        'created_at': ticket.created_at.isoformat() + 'Z',
        'assigned_at': ticket.assigned_at.isoformat() + 'Z' if ticket.assigned_at else None,
        'resolved_at': ticket.resolved_at.isoformat() + 'Z' if ticket.resolved_at else None,
        'closed_at': ticket.closed_at.isoformat() + 'Z' if ticket.closed_at else None,
        'sla_due_at': ticket.sla_due_at.isoformat() + 'Z', 'sla_status': sla_status(ticket),
    }
    if with_history:
        value['history'] = [{
            'action': h.action, 'actor': h.actor.full_name, 'note': h.note,
            'previous_status': h.previous_status, 'new_status': h.new_status,
            'occurred_at': h.occurred_at.isoformat() + 'Z',
        } for h in ticket.history]
    return value
