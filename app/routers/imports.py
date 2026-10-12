"""Read recent import batches and their rejected row diagnostics."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ImportBatch, RejectedRow, User
from app.security import require_roles
from app.services.import_service import batch_to_dict

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.get("")
def list_imports(limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db),
                 _admin: User = Depends(require_roles('Admin'))):
    batches = db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(limit)).all()
    return {"items": [batch_to_dict(batch) for batch in batches]}


@router.get("/{batch_id}/rejections")
def list_rejections(batch_id: int, db: Session = Depends(get_db),
                 _admin: User = Depends(require_roles('Admin'))):
    rows = db.scalars(select(RejectedRow).where(RejectedRow.import_batch_id == batch_id).order_by(RejectedRow.source_row_number)).all()
    return {"batch_id": batch_id, "items": [{
        "source_row_number": row.source_row_number,
        "claim_id": row.claim_id,
        "reason": row.failure_reason,
        "raw_data_json": row.raw_data_json,
    } for row in rows]}
