"""Task 5 consolidated Operations Jinja2 page; existing session and role policy."""
import os
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import (AuditEvent, BackupJob, CallLog, DeviceHealthCheck,
                        IVRRule, MonitoringEvent, NetworkCheck, Ticket, User)
from app.routers.pages import render
from app.security import require_roles

router = APIRouter(tags=['Task 5 browser'])


@router.get('/operations')
def operations_page(request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_roles('Admin','Technician'))):
    return render(request, 'operations.html', db,
        network=db.scalars(select(NetworkCheck).order_by(NetworkCheck.id.desc()).limit(20)).all(),
        health=db.scalars(select(DeviceHealthCheck).order_by(DeviceHealthCheck.id.desc()).limit(10)).all(),
        calls=db.scalars(select(CallLog).order_by(CallLog.occurred_at.desc()).limit(20)).all(),
        ivr=db.scalars(select(IVRRule).order_by(IVRRule.menu_name,IVRRule.digit)).all(),
        backups=db.scalars(select(BackupJob).order_by(BackupJob.id.desc()).limit(15)).all(),
        monitoring=db.scalars(select(MonitoringEvent).order_by(MonitoringEvent.id.desc()).limit(20)).all(),
        audit=db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(12)).all(),
        outstanding=db.scalars(select(Ticket).where(Ticket.status.not_in(['Resolved','Closed']))
                               .order_by(Ticket.id.desc()).limit(15)).all(),
        calls_total=db.scalar(select(func.count(CallLog.id))) or 0,
        calls_missed=db.scalar(select(func.count(CallLog.id)).where(CallLog.outcome=='Missed')) or 0,
        network_failed=db.scalar(select(func.count(NetworkCheck.id)).where(NetworkCheck.result=='Fail')) or 0,
        backup_success=db.scalars(select(BackupJob).where(BackupJob.result=='Success')
                .order_by(BackupJob.id.desc()).limit(1)).first(),
        allowed_tcp=os.getenv('OPS_TCP_TARGETS','localhost:8000'),
        allowed_dns=os.getenv('OPS_DNS_TARGETS','localhost'),
        admin=user.role=='Admin')
