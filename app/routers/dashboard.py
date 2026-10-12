"""Unified Task 1 claims and Task 2 helpdesk operations dashboard."""
from datetime import date
from pathlib import Path
from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Asset, AuditEvent, Claim, ImportBatch, Ticket, User, utc_now
from app.security import html_context

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / 'templates'))
router = APIRouter(tags=['dashboard'])


@router.get('/')
def dashboard(request: Request, db: Session = Depends(get_db)):
    ctx = html_context(request, db)
    user = ctx['user']
    if not user:
        return templates.TemplateResponse(request, 'login.html', ctx)
    scoped = select(Ticket)
    if user.role == 'Employee':
        scoped = scoped.where(Ticket.employee_id == user.id)
    elif user.role == 'Technician':
        scoped = scoped.where((Ticket.assigned_technician_id == user.id) | (Ticket.employee_id == user.id))
    ticket_rows = db.scalars(scoped).all()
    unresolved = [t for t in ticket_rows if t.status not in {'Resolved','Closed'}]
    it_stats = {
        'open_tickets': len(unresolved),
        'resolved_tickets': sum(t.status in {'Resolved','Closed'} for t in ticket_rows),
        'high_priority': sum(t.priority in {'High','Critical'} for t in unresolved),
        'overdue_tickets': sum(t.sla_due_at < utc_now() for t in unresolved),
        'assigned_devices': 0,
        'maintenance_devices': 0,
    }
    if user.role in {'Admin','Technician'}:
        it_stats['assigned_devices'] = db.scalar(select(func.count()).select_from(Asset).where(Asset.status == 'Assigned')) or 0
        it_stats['maintenance_devices'] = db.scalar(select(func.count()).select_from(Asset).where(Asset.status == 'Maintenance')) or 0
    else:
        it_stats['assigned_devices'] = db.scalar(select(func.count()).select_from(Asset).where(Asset.assigned_employee_id == user.id)) or 0
    events = []
    if user.role in {'Admin','Technician'}:
        # Limit metadata to the last 10 technical actions; never leak passwords.
        stmt = (select(AuditEvent, User.full_name).join(User, User.id == AuditEvent.actor_user_id)
                .where(User.role == 'Technician').order_by(AuditEvent.id.desc()).limit(10))
        events = [{'type': ev.event_type, 'technician': name, 'when': ev.occurred_at}
                  for ev, name in db.execute(stmt)]
    if user.role == 'Admin':
        claims = db.scalars(select(Claim).order_by(Claim.id.desc()).limit(20)).all()
        batches = db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(10)).all()
        total_claims = db.scalar(select(func.count()).select_from(Claim)) or 0
        total_claimed = db.scalar(select(func.sum(Claim.amount_gbp))) or 0
    else:
        claims, batches, total_claims, total_claimed = [], [], 0, 0
    return templates.TemplateResponse(request, 'dashboard.html', {
        **ctx, 'stats': it_stats, 'events': events, 'recent_tickets': ticket_rows[-10:][::-1],
        'claims': claims, 'batches': batches, 'total_claims': total_claims,
        'total_amount': f'{total_claimed:,.2f}',
    })
