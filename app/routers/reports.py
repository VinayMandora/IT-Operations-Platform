"""Downloadable formula-driven Excel workbook."""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import require_roles
from app.services.report_service import create_claims_workbook

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/claims.xlsx")
def download_claims_report(db: Session = Depends(get_db),
                           _admin: User = Depends(require_roles('Admin'))):
    report = create_claims_workbook(db)
    return StreamingResponse(
        report,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="northstar_claims_report.xlsx"'},
    )
