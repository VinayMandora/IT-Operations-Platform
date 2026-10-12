"""Task 4 Excel reporting endpoint; administrator only."""
from io import BytesIO
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User
from app.security import require_roles
from app.services.claim_report_service import build_report

router = APIRouter(tags=['Task 4 reports'])


@router.get('/api/reports/claims-workflows.xlsx')
def claims_workflow_report(db: Session = Depends(get_db),
                           _user: User = Depends(require_roles('Admin'))):
    return StreamingResponse(BytesIO(build_report(db)),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition':'attachment; filename="northstar-claims-workflows.xlsx"'})
