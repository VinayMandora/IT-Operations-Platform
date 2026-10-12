"""Excel report downloads for staff with IT operational reporting access."""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import require_roles
from app.services.it_report_service import inventory_report, tickets_report, workload_report

router = APIRouter(prefix='/api/reports', tags=['IT reports'])


def stream(workbook, name):
    return StreamingResponse(workbook,
       media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
       headers={'Content-Disposition': f'attachment; filename="northstar_{name}.xlsx"'})


@router.get('/tickets.xlsx')
def export_tickets(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin','Technician'))):
    return stream(tickets_report(db), 'tickets')


@router.get('/inventory.xlsx')
def export_assets(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin','Technician'))):
    return stream(inventory_report(db), 'inventory')


@router.get('/workload.xlsx')
def export_workload(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin'))):
    return stream(workload_report(db), 'technician_workload')
