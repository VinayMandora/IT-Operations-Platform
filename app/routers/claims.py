"""Claims import and paginated claims list endpoints."""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import MAX_UPLOAD_BYTES
from app.db import get_db
from app.models import Claim, User
from app.security import require_roles
from app.services.import_service import ImportConflictError, import_claims
from app.services.validation import FileValidationError

router = APIRouter(prefix="/api/claims", tags=["claims"])


@router.post("/import")
async def upload_claims(file: UploadFile = File(...), db: Session = Depends(get_db),
                        _admin: User = Depends(require_roles('Admin'))):
    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds configured maximum size")
    try:
        # Authorization performed a read and started SQLAlchemy autobegin; Task 1's
        # import service deliberately owns its transaction boundary.
        db.rollback()
        return import_claims(db, file.filename, data)
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("")
def get_claims(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles('Admin')),
):
    total = db.scalar(select(func.count()).select_from(Claim)) or 0
    claims = db.scalars(select(Claim).order_by(Claim.id).offset(offset).limit(limit)).all()
    return {
        "total": total, "offset": offset, "limit": limit,
        "items": [{
            "claim_id": claim.claim_id,
            "policy_number": claim.policy_number,
            "claimant_name": claim.claimant_name,
            "claim_type": claim.claim_type,
            "incident_date": claim.incident_date.isoformat(),
            "reported_date": claim.reported_date.isoformat(),
            "status": claim.status,
            "amount_gbp": str(claim.amount_gbp),
            "postcode": claim.postcode,
            "description": claim.description,
            "import_batch_id": claim.import_batch_id,
        } for claim in claims],
    }
