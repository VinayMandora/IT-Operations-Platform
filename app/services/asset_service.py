"""Device lifecycle helpers and optimistic conditional updates for assignments."""
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Asset, AssetMovement, User, utc_now
from app.services.helpdesk_service import log_event


def asset_dict(asset: Asset) -> dict:
    return {
        'id': asset.id, 'asset_tag': asset.asset_tag, 'serial_number': asset.serial_number,
        'device_type': asset.device_type, 'manufacturer': asset.manufacturer,
        'model': asset.model, 'operating_system': asset.operating_system,
        'purchase_date': asset.purchase_date.isoformat(),
        'warranty_expiry': asset.warranty_expiry.isoformat() if asset.warranty_expiry else None,
        'assigned_employee_id': asset.assigned_employee_id,
        'assigned_employee': asset.assigned_employee.full_name if asset.assigned_employee else None,
        'assigned_at': asset.assigned_at.isoformat() + 'Z' if asset.assigned_at else None,
        'status': asset.status, 'notes': asset.notes,
    }


def change_assignment(db: Session, asset: Asset, employee: User | None, actor: User):
    # A single UPDATE with a WHERE condition is atomic on SQL Server and prevents
    # two concurrent technicians from assigning one device to different employees.
    if employee:
        stmt = (update(Asset).where(Asset.id == asset.id, Asset.status == 'Available',
                                  Asset.assigned_employee_id.is_(None))
                .values(status='Assigned', assigned_employee_id=employee.id, assigned_at=utc_now()))
        verb, action = 'ASSIGNED', 'ASSET_ASSIGNED'
    else:
        if asset.assigned_employee_id is None:
            raise HTTPException(409, 'Asset is not assigned')
        prior_id = asset.assigned_employee_id
        stmt = (update(Asset).where(Asset.id == asset.id, Asset.status == 'Assigned',
                                  Asset.assigned_employee_id == prior_id)
                .values(status='Available', assigned_employee_id=None, assigned_at=None))
        verb, action = 'RETURNED', 'ASSET_RETURNED'
    # SQLAlchemy's synchronize_session=False prevents stale in-memory status updates.
    result = db.execute(stmt.execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, 'Assignment conflict: asset state changed or is unavailable')
    employee_id = employee.id if employee else prior_id
    db.add(AssetMovement(asset_id=asset.id, employee_id=employee_id, actor_user_id=actor.id, action=verb))
    log_event(db, action, actor, asset_id=asset.id, employee_id=employee_id)
    db.flush()
    db.expire(asset)
    return asset
