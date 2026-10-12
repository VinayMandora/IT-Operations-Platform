"""Browser pages reuse the existing session and role permissions."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Asset, AssetReservation, Employee, OffboardingRequest, ProvisioningAction, User
from app.routers.pages import render
from app.security import require_roles
from app.services.employee_service import DEPARTMENT_GROUPS

router = APIRouter(tags=['employee browser pages'])


@router.get('/employees')
def index(request: Request, db: Session = Depends(get_db),
          user: User = Depends(require_roles('Admin','Technician'))):
    employees = db.scalars(select(Employee).order_by(Employee.id.desc()).limit(200)).all()
    offboards = db.scalars(select(OffboardingRequest).order_by(OffboardingRequest.id.desc()).limit(100)).all()
    actions = db.scalars(select(ProvisioningAction).order_by(ProvisioningAction.id.desc()).limit(100)).all()
    reservations = db.scalars(select(AssetReservation).where(AssetReservation.status == 'Reserved')).all()
    assigned_assets = db.scalars(select(Asset).where(Asset.status == 'Assigned').order_by(Asset.asset_tag)).all()
    stats = {
        'active': sum(e.status == 'Active' for e in employees),
        'pending_onboarding': sum(e.status == 'Prepared' for e in employees),
        'pending_offboarding': sum(r.status == 'PendingApproval' for r in offboards),
        'failed': sum(a.status == 'Failed' for a in actions),
        'reserved': len(reservations),
        'assigned_devices': len(assigned_assets),
    }
    return render(request, 'employees.html', db, employees=employees, offboards=offboards,
                  activities=actions[:20], stats=stats, groups=DEPARTMENT_GROUPS,
                  assigned_assets=assigned_assets, admin=(user.role == 'Admin'))
