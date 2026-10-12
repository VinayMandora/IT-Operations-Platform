"""RBAC and CSRF-protected Task 5 endpoints. No live PBX or shell commands from request data."""
import json
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import (AuditEvent, BackupJob, CallLog, DeviceHealthCheck, IVRRule,
                        MonitoringEvent, NetworkCheck, Ticket, User)
from app.operations_schemas import DiagnosticRequest, IVRUpdate, IVRSimulate, ExportRequest, FailureRequest
from app.security import require_roles
from app.services.operations_service import run_network_check, save_health
from app.services.phone_service import import_call_csv, upsert_ivr, simulate_ivr
from app.services.backup_service import export_records, verify_export, simulate_backup_failure, safe_path

router = APIRouter(prefix='/api/operations', tags=['Task 5 operations'])


def _row(row):
    return {c.name:getattr(row,c.name) for c in row.__table__.columns}


@router.post('/network/check')
def network_check(value: DiagnosticRequest, db: Session = Depends(get_db),
                  actor: User = Depends(require_roles('Admin','Technician'))):
    return jsonable_encoder(_row(run_network_check(db, actor, value.kind, value.target, value.port)))


@router.get('/network/history')
def network_history(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin','Technician'))):
    return jsonable_encoder([_row(c) for c in db.scalars(select(NetworkCheck).order_by(NetworkCheck.id.desc()).limit(100))])


@router.post('/health/check')
def health_check(db: Session = Depends(get_db), actor: User = Depends(require_roles('Admin','Technician'))):
    return jsonable_encoder(_row(save_health(db, actor)))


@router.get('/health/history')
def health_history(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin','Technician'))):
    return jsonable_encoder([_row(c) for c in db.scalars(select(DeviceHealthCheck).order_by(DeviceHealthCheck.id.desc()).limit(100))])


@router.post('/calls/import')
async def upload_calls(file: UploadFile = File(...), db: Session = Depends(get_db),
                       actor: User = Depends(require_roles('Admin'))):
    if not file.filename or Path(file.filename).suffix.lower() != '.csv':
        raise HTTPException(422, 'Only .csv files are accepted')
    data = await file.read(1_000_001)
    return import_call_csv(db, actor, data)


@router.get('/calls')
def calls(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin','Technician'))):
    return jsonable_encoder([_row(c) for c in db.scalars(select(CallLog).order_by(CallLog.occurred_at.desc()).limit(200))])


@router.get('/calls/stats')
def call_stats(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin','Technician'))):
    return {'total': db.scalar(select(func.count(CallLog.id))) or 0,
            'missed': db.scalar(select(func.count(CallLog.id)).where(CallLog.outcome=='Missed')) or 0,
            'answered': db.scalar(select(func.count(CallLog.id)).where(CallLog.outcome=='Answered')) or 0,
            'voicemail': db.scalar(select(func.count(CallLog.id)).where(CallLog.outcome=='Voicemail')) or 0}


@router.get('/ivr')
def ivr_rules(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin','Technician'))):
    return jsonable_encoder([_row(r) for r in db.scalars(select(IVRRule).order_by(IVRRule.menu_name,IVRRule.digit))])


@router.put('/ivr')
def update_ivr(value: IVRUpdate, db: Session = Depends(get_db), actor: User = Depends(require_roles('Admin'))):
    return jsonable_encoder(_row(upsert_ivr(db, actor, value)))


@router.post('/ivr/simulate')
def simulate(value: IVRSimulate, db: Session = Depends(get_db),
             _user: User = Depends(require_roles('Admin','Technician'))):
    return simulate_ivr(db, value.menu_name, value.digit)


@router.post('/backups/export')
def make_export(value: ExportRequest, db: Session = Depends(get_db), actor: User = Depends(require_roles('Admin'))):
    return jsonable_encoder(_row(export_records(db, actor, value.tables)))


@router.get('/backups')
def backup_history(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin','Technician'))):
    return jsonable_encoder([_row(r) for r in db.scalars(select(BackupJob).order_by(BackupJob.id.desc()).limit(100))])


@router.post('/backups/{job_id}/verify')
def verify(job_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles('Admin'))):
    job = db.get(BackupJob,job_id)
    if not job: raise HTTPException(404, 'Backup record not found')
    return verify_export(db, actor, job)


@router.get('/backups/{job_id}/download')
def download(job_id: int, db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin'))):
    job = db.get(BackupJob,job_id)
    if not job: raise HTTPException(404, 'Backup record not found')
    path = safe_path(job)
    if not path.is_file(): raise HTTPException(404, 'Backup file missing')
    return FileResponse(path, filename=path.name, media_type='application/zip')


@router.post('/backups/simulate-failure')
def fail_backup(value: FailureRequest, db: Session = Depends(get_db), actor: User = Depends(require_roles('Admin'))):
    return jsonable_encoder(_row(simulate_backup_failure(db, actor, value.reason)))


@router.get('/monitoring/events')
def monitor_events(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin','Technician'))):
    return jsonable_encoder([_row(e) for e in db.scalars(select(MonitoringEvent).order_by(MonitoringEvent.id.desc()).limit(100))])
