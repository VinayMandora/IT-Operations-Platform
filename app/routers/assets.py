"""Inventory CRUD, searching/filtering, assignment and return tracking."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Asset, User
from app.schemas import AssetAssign, AssetCreate, AssetEdit
from app.security import require_roles
from app.services.asset_service import asset_dict, change_assignment
from app.services.helpdesk_service import log_event

router = APIRouter(prefix='/api/assets', tags=['asset inventory'])


def asset_query():
    return select(Asset).options(selectinload(Asset.assigned_employee))


@router.get('')
def list_assets(q: str = Query('', max_length=100), status: str | None = None,
                device_type: str | None = None, offset: int = Query(0, ge=0),
                limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
                _user: User = Depends(require_roles('Admin','Technician'))):
    query = asset_query()
    if q:
        pattern = '%' + q.replace('%', r'\%').replace('_', r'\_') + '%'
        query = query.where(or_(Asset.asset_tag.ilike(pattern, escape='\\'),
                                Asset.serial_number.ilike(pattern, escape='\\'),
                                Asset.model.ilike(pattern, escape='\\')))
    if status:
        query = query.where(Asset.status == status)
    if device_type:
        query = query.where(Asset.device_type == device_type)
    return {'items': [asset_dict(a) for a in db.scalars(query.order_by(Asset.id).offset(offset).limit(limit))],
            'offset': offset, 'limit': limit}


@router.post('', status_code=201)
def create_asset(body: AssetCreate, db: Session = Depends(get_db),
                 user: User = Depends(require_roles('Admin','Technician'))):
    asset = Asset(**body.model_dump(), status='Available')
    try:
        db.add(asset)
        db.flush()
        log_event(db, 'ASSET_CREATED', user, asset_id=asset.id, asset_tag=asset.asset_tag)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Asset tag or serial number already exists') from exc
    return asset_dict(db.scalar(asset_query().where(Asset.id == asset.id)))


@router.get('/{asset_id}')
def get_asset(asset_id: int, db: Session = Depends(get_db),
              _user: User = Depends(require_roles('Admin','Technician'))):
    asset = db.scalar(asset_query().where(Asset.id == asset_id))
    if not asset:
        raise HTTPException(404, 'Asset not found')
    return asset_dict(asset)


@router.patch('/{asset_id}')
def edit_asset(asset_id: int, body: AssetEdit, db: Session = Depends(get_db),
               user: User = Depends(require_roles('Admin','Technician'))):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, 'Asset not found')
    changes = body.model_dump(exclude_unset=True)
    if changes.get('status') and (asset.assigned_employee_id is not None or asset.status == 'Reserved'):
        raise HTTPException(409, 'Return the assigned device before changing status')
    if changes.get('warranty_expiry') and changes['warranty_expiry'] < asset.purchase_date:
        raise HTTPException(422, 'Warranty expiry is earlier than purchase date')
    for field, value in changes.items():
        setattr(asset, field, value)
    log_event(db, 'ASSET_UPDATED', user, asset_id=asset.id, changes=changes)
    db.commit()
    return asset_dict(db.scalar(asset_query().where(Asset.id == asset_id)))


@router.post('/{asset_id}/assign')
def assign_asset(asset_id: int, body: AssetAssign, db: Session = Depends(get_db),
                 user: User = Depends(require_roles('Admin','Technician'))):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, 'Asset not found')
    employee = db.get(User, body.employee_id)
    if not employee or employee.role != 'Employee' or not employee.is_active:
        raise HTTPException(422, 'An active Employee is required')
    change_assignment(db, asset, employee, user)
    db.commit()
    return asset_dict(db.scalar(asset_query().where(Asset.id == asset_id)))


@router.post('/{asset_id}/return')
def return_asset(asset_id: int, db: Session = Depends(get_db),
                 user: User = Depends(require_roles('Admin','Technician'))):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, 'Asset not found')
    change_assignment(db, asset, None, user)
    db.commit()
    return asset_dict(db.scalar(asset_query().where(Asset.id == asset_id)))
