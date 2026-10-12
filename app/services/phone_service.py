"""CSV ingestion and deterministic IVR simulation; never contacts a PBX."""
import csv
from datetime import datetime, timezone, timedelta
from io import StringIO
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import CallLog, IVRRule, User, utc_now
from app.services.helpdesk_service import log_event
from app.services.operations_service import _event

FIELDS = {'call_reference','extension','occurred_at','direction','duration_seconds','route','outcome'}


def _parse(row: dict) -> dict:
    reference = (row.get('call_reference') or '').strip()
    extension = (row.get('extension') or '').strip()
    route = (row.get('route') or '').strip()
    if not (2 <= len(reference) <= 50 and reference.replace('-','').replace('_','').isalnum()):
        raise ValueError('Invalid call reference')
    if not (1 <= len(extension) <= 12 and extension.isdecimal()):
        raise ValueError('Invalid extension')
    if not (1 <= len(route) <= 120 and all(c.isalnum() or c in ' _-' for c in route)):
        raise ValueError('Invalid route')
    direction = (row.get('direction') or '').strip().title()
    outcome = (row.get('outcome') or '').strip().title()
    if direction not in ('Inbound','Outbound') or outcome not in ('Answered','Missed','Voicemail'):
        raise ValueError('Invalid direction or outcome')
    try:
        duration = int((row.get('duration_seconds') or '').strip())
        date_value = datetime.fromisoformat((row.get('occurred_at') or '').strip().replace('Z','+00:00'))
    except (ValueError, TypeError):
        raise ValueError('Invalid timestamp or duration') from None
    if date_value.tzinfo:
        date_value = date_value.astimezone(timezone.utc).replace(tzinfo=None)
    if not 0 <= duration <= 86400 or date_value.year < 2020 or date_value > datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=365):
        raise ValueError('Out-of-range timestamp or duration')
    return dict(call_reference=reference, extension=extension, occurred_at=date_value,
                direction=direction, duration_seconds=duration, route=route, outcome=outcome)


def import_call_csv(db: Session, actor: User, data: bytes) -> dict:
    if not data or len(data) > 1_000_000 or b'\x00' in data:
        raise HTTPException(422, 'Empty, binary or oversized CSV (1 MB max)')
    try:
        reader = csv.DictReader(StringIO(data.decode('utf-8-sig'), newline=''))
        if reader.fieldnames is None or set(reader.fieldnames) != FIELDS:
            raise HTTPException(422, 'CSV column names do not match the required schema')
        lines = list(reader)
    except UnicodeDecodeError:
        raise HTTPException(422, 'CSV must be UTF-8') from None
    if not lines or len(lines) > 5000:
        raise HTTPException(422, 'CSV must contain between 1 and 5000 call rows')
    existing = set(db.scalars(select(CallLog.call_reference)).all())
    inserted = 0; duplicates = 0; rejected = []
    for line_no, row in enumerate(lines, 2):
        try:
            parsed = _parse(row)
            if parsed['call_reference'] in existing:
                duplicates += 1
                continue
            db.add(CallLog(**parsed))
            existing.add(parsed['call_reference']); inserted += 1
        except (ValueError, TypeError) as exc:
            rejected.append({'row': line_no, 'reason': str(exc)})
    _event(db, actor, 'CallImport', 'Warning' if rejected else 'Info', 'csv',
           f'Call import: {inserted} inserted, {duplicates} duplicate, {len(rejected)} rejected')
    log_event(db, 'CALLS_IMPORTED', actor, inserted=inserted, duplicates=duplicates, rejected=len(rejected))
    db.commit()
    return {'total':len(lines), 'inserted':inserted, 'duplicates':duplicates,
            'rejected_count':len(rejected), 'rejections':rejected[:100]}


def upsert_ivr(db: Session, actor: User, value) -> IVRRule:
    rule = db.scalar(select(IVRRule).where(IVRRule.menu_name == value.menu_name, IVRRule.digit == value.digit))
    previous = {'destination':rule.destination, 'enabled':rule.enabled} if rule else None
    if not rule:
        rule = IVRRule(menu_name=value.menu_name, digit=value.digit)
        db.add(rule)
    for field in ('label','destination_type','destination','enabled'):
        setattr(rule, field, getattr(value, field))
    rule.updated_at = utc_now(); rule.updated_by = actor.id
    db.flush()
    _event(db, actor, 'IVRChanged', 'Info', str(rule.id),
           f'Rule {rule.menu_name}/{rule.digit} updated: {rule.destination}')
    log_event(db, 'IVR_UPDATED', actor, rule_id=rule.id, previous=previous,
              destination=rule.destination, enabled=rule.enabled)
    db.commit(); db.refresh(rule)
    return rule


def simulate_ivr(db: Session, menu: str, digit: str) -> dict:
    rule = db.scalar(select(IVRRule).where(IVRRule.menu_name == menu,
                                         IVRRule.digit == digit, IVRRule.enabled.is_(True)))
    if not rule:
        return {'result':'Unrouted', 'menu':menu, 'digit':digit, 'reason':'No enabled match; mock call was not placed'}
    return {'result':'Routed (simulation)', 'menu':menu, 'digit':digit,
            'destination_type':rule.destination_type, 'destination':rule.destination,
            'label':rule.label, 'real_call_placed':False}
