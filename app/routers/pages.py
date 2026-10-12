"""Jinja2 browser pages for Task 2, sharing the Task 1 dashboard."""
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Asset, Ticket, User
from app.security import current_user, html_context, require_roles
from app.services.helpdesk_service import require_ticket

router = APIRouter(tags=['browser pages'])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / 'templates'))


def render(request, name, db, **data):
    return templates.TemplateResponse(request, name, {**html_context(request, db), **data})


@router.get('/login')
def login_page(request: Request, db: Session = Depends(get_db)):
    return render(request, 'login.html', db)


@router.get('/tickets')
def tickets_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(Ticket).order_by(Ticket.id.desc()).limit(100)
    if user.role == 'Employee':
        query = query.where(Ticket.employee_id == user.id)
    elif user.role == 'Technician':
        query = query.where((Ticket.assigned_technician_id == user.id) | (Ticket.employee_id == user.id))
    return render(request, 'tickets.html', db, tickets=db.scalars(query).all())


@router.get('/tickets/new')
def new_ticket_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    assets = db.scalars(select(Asset).where(Asset.assigned_employee_id == user.id)).all() if user.role == 'Employee' else db.scalars(select(Asset)).all()
    employees = db.scalars(select(User).where(User.role == 'Employee', User.is_active == True)).all() if user.role == 'Admin' else []
    return render(request, 'ticket_new.html', db, assets=assets, employees=employees)


@router.get('/tickets/{ticket_id}')
def ticket_page(ticket_id: int, request: Request, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    ticket = require_ticket(user, db.get(Ticket, ticket_id))
    technicians = db.scalars(select(User).where(User.role == 'Technician', User.is_active == True)).all() if user.role == 'Admin' else []
    can_update = user.role == 'Admin' or (user.role == 'Technician' and ticket.assigned_technician_id == user.id)
    can_assign = user.role == 'Admin' or (user.role == 'Technician' and ticket.assigned_technician_id in (None, user.id))
    return render(request, 'ticket_detail.html', db, ticket=ticket,
                  technicians=technicians, can_update=can_update, can_assign=can_assign)


@router.get('/assets')
def assets_page(request: Request, db: Session = Depends(get_db),
                _user: User = Depends(require_roles('Admin','Technician'))):
    assets = db.scalars(select(Asset).order_by(Asset.asset_tag)).all()
    employees = db.scalars(select(User).where(User.role == 'Employee', User.is_active == True)).all()
    return render(request, 'assets.html', db, assets=assets, employees=employees)


@router.get('/users')
def users_page(request: Request, db: Session = Depends(get_db),
               _user: User = Depends(require_roles('Admin'))):
    return render(request, 'users.html', db, users=db.scalars(select(User).order_by(User.id)).all())
