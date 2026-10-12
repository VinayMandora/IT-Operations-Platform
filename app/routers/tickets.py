"""Ticket submission, ownership filters, technician workflow and immutable history."""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Asset, Ticket, TicketHistory, User, utc_now
from app.schemas import TicketAssign, TicketCreate, TicketNote, TicketUpdate
from app.security import current_user, require_roles
from app.services.helpdesk_service import (SLA_HOURS, TRANSITIONS, log_event,
                                           require_ticket, ticket_dict, ticket_history)

router = APIRouter(prefix='/api/tickets', tags=['helpdesk tickets'])


def ticket_query():
    return select(Ticket).options(selectinload(Ticket.employee), selectinload(Ticket.technician),
                                  selectinload(Ticket.asset),
                                  selectinload(Ticket.history).selectinload(TicketHistory.actor))


@router.post('', status_code=201)
def create_ticket(body: TicketCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    employee_id = user.id
    if body.employee_id is not None:
        if user.role != 'Admin':
            raise HTTPException(403, 'Only admins can submit on behalf of an employee')
        target = db.get(User, body.employee_id)
        if not target or not target.is_active or target.role != 'Employee':
            raise HTTPException(422, 'employee_id must refer to an active Employee')
        employee_id = target.id
    if body.affected_asset_id:
        asset = db.get(Asset, body.affected_asset_id)
        if not asset:
            raise HTTPException(422, 'Asset not found')
        if user.role == 'Employee' and asset.assigned_employee_id != user.id:
            raise HTTPException(403, 'You may only report a device assigned to you')
    now = utc_now()
    ticket = Ticket(employee_id=employee_id, affected_asset_id=body.affected_asset_id,
                    title=body.title, description=body.description, category=body.category,
                    priority=body.priority, status='Open', created_at=now,
                    sla_due_at=now + timedelta(hours=SLA_HOURS[body.priority]))
    db.add(ticket)
    db.flush()
    ticket_history(db, ticket, user, 'Created', note=body.description, new='Open')
    log_event(db, 'TICKET_CREATED', user, ticket_id=ticket.id, reference=ticket.reference)
    db.commit()
    return ticket_dict(db.scalar(ticket_query().where(Ticket.id == ticket.id)), with_history=True)


@router.get('')
def list_tickets(status: str | None = None, priority: str | None = None,
                 limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = ticket_query()
    if user.role == 'Employee':
        query = query.where(Ticket.employee_id == user.id)
    elif user.role == 'Technician':
        query = query.where((Ticket.assigned_technician_id == user.id) | (Ticket.employee_id == user.id))
    if status:
        query = query.where(Ticket.status == status)
    if priority:
        query = query.where(Ticket.priority == priority)
    tickets = db.scalars(query.order_by(Ticket.id.desc()).offset(offset).limit(limit)).all()
    return {'items': [ticket_dict(t) for t in tickets], 'count': len(tickets),
            'offset': offset, 'limit': limit}


@router.get('/{ticket_id}')
def detail(ticket_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ticket = require_ticket(user, db.scalar(ticket_query().where(Ticket.id == ticket_id)))
    return ticket_dict(ticket, with_history=True)


@router.post('/{ticket_id}/assign')
def assign(ticket_id: int, body: TicketAssign, db: Session = Depends(get_db),
           user: User = Depends(require_roles('Admin','Technician'))):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(404, 'Ticket not found')
    if user.role == 'Technician' and body.technician_id != user.id:
        raise HTTPException(403, 'Technicians may only claim tickets for themselves')
    if ticket.status not in {'Open', 'Assigned'}:
        raise HTTPException(409, 'Only Open or Assigned tickets can be assigned')
    if user.role == 'Technician' and ticket.assigned_technician_id not in {None, user.id}:
        raise HTTPException(409, 'Ticket is already assigned to another technician')
    technician = db.get(User, body.technician_id)
    if not technician or technician.role != 'Technician' or not technician.is_active:
        raise HTTPException(422, 'An active Technician is required')
    previous = ticket.status
    # Compare-and-swap assignment also prevents concurrent self-claim collisions.
    stmt = update(Ticket).where(Ticket.id == ticket.id, Ticket.status.in_(['Open','Assigned']))
    if user.role == 'Technician':
        stmt = stmt.where((Ticket.assigned_technician_id.is_(None)) |
                          (Ticket.assigned_technician_id == user.id))
    result = db.execute(stmt.values(assigned_technician_id=technician.id, status='Assigned',
                                    assigned_at=utc_now()).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, 'Ticket assignment changed concurrently')
    db.expire(ticket)
    ticket_history(db, ticket, user, 'Assigned', f'Assigned to {technician.full_name}', previous, 'Assigned')
    log_event(db, 'TICKET_ASSIGNED', user, ticket_id=ticket.id, technician_id=technician.id)
    db.commit()
    return ticket_dict(db.scalar(ticket_query().where(Ticket.id == ticket_id)), with_history=True)


@router.patch('/{ticket_id}')
def update_ticket(ticket_id: int, body: TicketUpdate, db: Session = Depends(get_db),
                  user: User = Depends(require_roles('Admin','Technician'))):
    ticket = require_ticket(user, db.get(Ticket, ticket_id), write=True)
    if body.status not in TRANSITIONS[ticket.status]:
        raise HTTPException(409, f'Invalid status transition: {ticket.status} -> {body.status}')
    if body.status in {'Assigned', 'In Progress', 'Resolved', 'Closed'} and not ticket.assigned_technician_id:
        raise HTTPException(409, 'Ticket needs an assigned technician')
    if body.status == 'Resolved' and (not body.resolution_details or len(body.resolution_details.strip()) < 10):
        raise HTTPException(422, 'Provide at least 10 characters of resolution_details')
    previous = ticket.status
    ticket.status = body.status
    if body.status == 'Resolved':
        ticket.resolved_at = utc_now()
        ticket.resolution_details = body.resolution_details
    if body.status == 'In Progress' and previous == 'Resolved':
        ticket.resolved_at = None
        ticket.resolution_details = None
    if body.status == 'Closed':
        ticket.closed_at = utc_now()
    ticket_history(db, ticket, user, 'Status change', body.resolution_details or '', previous, body.status)
    log_event(db, 'TICKET_UPDATED', user, ticket_id=ticket.id, from_status=previous, to_status=body.status)
    db.commit()
    return ticket_dict(db.scalar(ticket_query().where(Ticket.id == ticket_id)), with_history=True)


@router.post('/{ticket_id}/notes', status_code=201)
def add_note(ticket_id: int, body: TicketNote, db: Session = Depends(get_db),
             user: User = Depends(require_roles('Admin','Technician'))):
    ticket = require_ticket(user, db.get(Ticket, ticket_id), write=True)
    if ticket.status == 'Closed':
        raise HTTPException(409, 'Closed tickets are read-only')
    ticket_history(db, ticket, user, 'Troubleshooting note', body.note)
    log_event(db, 'TICKET_NOTE', user, ticket_id=ticket.id)
    db.commit()
    return ticket_dict(db.scalar(ticket_query().where(Ticket.id == ticket_id)), with_history=True)
