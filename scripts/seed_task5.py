"""Idempotent fictional call/IVR seed; optional local mock health snapshot."""
from pathlib import Path
from sqlalchemy import select
from app.db import get_engine
from app.models import (IVRRule, User, NetworkCheck, DeviceHealthCheck, MonitoringEvent, utc_now)
from app.operations_schemas import IVRUpdate
from app.services.phone_service import import_call_csv, upsert_ivr
from sqlalchemy.orm import Session

RULES = [
    ('Main','1','Claims enquiries','Queue','ClaimsQueue'),
    ('Main','2','IT support','Queue','ITSupport'),
    ('Main','0','Reception','Extension','100'),
    ('AfterHours','1','Leave a message','Voicemail','ClaimsMailbox'),
]


def main():
    with Session(get_engine()) as db:
        admin = db.scalar(select(User).where(User.username=='admin'))
        if admin is None:
            raise RuntimeError('Run scripts.seed_task2 before Task 5 seeding')
        path = Path(__file__).resolve().parents[1] / 'sample_data' / 'task5_call_logs.csv'
        summary = import_call_csv(db, admin, path.read_bytes())
        if db.scalar(select(NetworkCheck.id).limit(1)) is None:
            db.add(NetworkCheck(check_type='DNS', target='localhost', result='Pass',
                elapsed_ms=2.5, details_json='{"mock":true,"addresses":["127.0.0.1"]}',
                actor_user_id=admin.id, created_at=utc_now()))
        if db.scalar(select(DeviceHealthCheck.id).limit(1)) is None:
            db.add(DeviceHealthCheck(hostname='NORTHSTAR-WIN11-LAB', os_description='Windows 11 Pro (fictional)',
                antivirus_status='Enabled', realtime_protection='Enabled', definitions_age_days=1,
                disk_total_bytes=512000000000, disk_free_bytes=240000000000,
                status='Healthy',details_json='{"mock":true}',actor_user_id=admin.id,created_at=utc_now()))
        if db.scalar(select(MonitoringEvent.id).where(MonitoringEvent.source_reference=='task5-mock-seed').limit(1)) is None:
            db.add(MonitoringEvent(event_type='MockSeed', severity='Info',
                source_reference='task5-mock-seed', message='Fictional lab network and Defender status seeded',
                actor_user_id=admin.id))
        db.commit()
        for menu,digit,label,kind,dest in RULES:
            existing = db.scalar(select(IVRRule).where(IVRRule.menu_name==menu,IVRRule.digit==digit))
            if existing is None:
                upsert_ivr(db, admin, IVRUpdate(menu_name=menu,digit=digit,label=label,
                                                destination_type=kind,destination=dest))
    print(f'Task 5 fictional seed ready: {summary["inserted"]} calls inserted, '
          f'{summary["duplicates"]} already present; {len(RULES)} IVR options.')


if __name__=='__main__': main()
