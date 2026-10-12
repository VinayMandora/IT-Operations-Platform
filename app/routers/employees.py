"""Authenticated employee lifecycle API; all external provisioning remains mocked."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.employee_schemas import ApprovalIn, OffboardIn, OnboardIn
from app.models import Employee, OffboardingRequest, OnboardingRequest, ProvisioningAction, User
from app.security import require_roles
from app.services.employee_service import (activate, ad_plan, approve_offboarding,
    create_onboarding, employee_dict, request_offboarding)

router = APIRouter(prefix='/api/employees', tags=['employee lifecycle'])


@router.get('')
def list_employees(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin','Technician'))):
    return {'items': [employee_dict(db, e) for e in db.scalars(select(Employee).order_by(Employee.id.desc()).limit(200))]}


@router.get('/metrics')
def metrics(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin','Technician'))):
    return {
        'active_employees': db.scalar(select(func.count()).select_from(Employee).where(Employee.status == 'Active')) or 0,
        'pending_onboarding': db.scalar(select(func.count()).select_from(OnboardingRequest).where(OnboardingRequest.status.in_(['Prepared','Attention']))) or 0,
        'pending_offboarding': db.scalar(select(func.count()).select_from(OffboardingRequest).where(OffboardingRequest.status == 'PendingApproval')) or 0,
        'failed_operations': db.scalar(select(func.count()).select_from(ProvisioningAction).where(ProvisioningAction.status == 'Failed')) or 0,
    }


@router.post('/onboarding', status_code=201)
def submit_onboarding(body: OnboardIn, db: Session = Depends(get_db),
                      user: User = Depends(require_roles('Admin'))):
    try:
        return create_onboarding(db, body, user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Employee identity or reservation conflict') from exc


@router.get('/offboarding')
def list_offboarding(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin','Technician'))):
    return {'items': [{'id': r.id, 'employee_id': r.employee_id, 'employee': r.employee.full_name,
                       'status': r.status, 'requested_by': r.requested_by,
                       'approved_by': r.approved_by, 'reason': r.reason}
                      for r in db.scalars(select(OffboardingRequest).order_by(OffboardingRequest.id.desc()).limit(200))]}


@router.get('/{employee_id}')
def get_employee(employee_id: int, db: Session = Depends(get_db),
                 _user: User = Depends(require_roles('Admin','Technician'))):
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(404, 'Employee not found')
    return employee_dict(db, employee)


@router.get('/{employee_id}/ad-plan')
def get_ad_plan(employee_id: int, db: Session = Depends(get_db),
                _user: User = Depends(require_roles('Admin'))):
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(404, 'Employee not found')
    return ad_plan(employee, db)


@router.post('/{employee_id}/activate')
def activate_employee(employee_id: int, db: Session = Depends(get_db),
                      user: User = Depends(require_roles('Admin'))):
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(404, 'Employee not found')
    return activate(db, employee, user)


@router.post('/{employee_id}/offboarding', status_code=201)
def submit_offboarding(employee_id: int, body: OffboardIn, db: Session = Depends(get_db),
                       user: User = Depends(require_roles('Admin','Technician'))):
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(404, 'Employee not found')
    request = request_offboarding(db, employee, body, user)
    return {'id': request.id, 'employee_id': employee_id, 'status': request.status,
            'message': 'Awaiting a different administrator\'s approval; no external account changes'}


@router.post('/offboarding/{request_id}/approve')
def approve_request(request_id: int, body: ApprovalIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles('Admin'))):
    request = db.get(OffboardingRequest, request_id)
    if not request:
        raise HTTPException(404, 'Offboarding request not found')
    try:
        request = approve_offboarding(db, request, user, body.comment)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Offboarding approval conflict') from exc
    return {'id': request.id, 'status': request.status, 'employee_id': request.employee_id,
            'simulation': True, 'message': 'Mock suspension complete; real accounts unchanged'}
