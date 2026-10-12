"""Employee lifecycle: safe plans, mock-only provisioning, asset reservation and approvals."""
import json
from datetime import date
from fastapi import HTTPException
from sqlalchemy import and_, select, update
from sqlalchemy.orm import Session

from app.models import (Employee, OnboardingRequest, OffboardingRequest, ProvisioningAction,
                        ApprovalRecord, Asset, AssetReservation, User, utc_now)
from app.services.google_directory import MockDirectory
from app.services.helpdesk_service import log_event

DEPARTMENT_GROUPS = {
    'Claims': ['SG-Claims-Read', 'SG-Claims-Write'],
    'Operations': ['SG-Operations-Read'],
    'Finance': ['SG-Finance-Read'],
    'HR': ['SG-HR-Read'],
    'IT': ['SG-IT-Helpdesk'],
}
GOOGLE_GROUPS = {
    'Claims': 'claims-team@northstar.example',
    'Operations': 'operations-team@northstar.example',
    'Finance': 'finance-team@northstar.example',
    'HR': 'hr-team@northstar.example',
    'IT': 'it-team@northstar.example',
}


def record(db, employee_id, kind, target, status, detail, *, onboard_id=None, offboard_id=None):
    item = ProvisioningAction(employee_id=employee_id, onboarding_request_id=onboard_id,
                              offboarding_request_id=offboard_id, action_type=kind,
                              target=target, status=status, result_detail=detail)
    db.add(item)
    return item


def employee_dict(db: Session, employee: Employee):
    onboarding = db.scalar(select(OnboardingRequest).where(OnboardingRequest.employee_id == employee.id))
    reservation = db.scalar(select(AssetReservation).where(
        AssetReservation.employee_id == employee.id, AssetReservation.status == 'Reserved'))
    actions = db.scalars(select(ProvisioningAction).where(ProvisioningAction.employee_id == employee.id)
                         .order_by(ProvisioningAction.id)).all()
    return {
        'id': employee.id, 'full_name': employee.full_name,
        'department': employee.department, 'job_title': employee.job_title,
        'manager_name': employee.manager_name, 'start_date': employee.start_date.isoformat(),
        'work_email': employee.work_email, 'ad_username': employee.ad_username,
        'status': employee.status, 'onboarding_status': onboarding.status if onboarding else None,
        'reserved_asset_tag': reservation.asset.asset_tag if reservation else None,
        'actions': [{'id': a.id, 'type': a.action_type, 'target': a.target,
                     'status': a.status, 'detail': a.result_detail} for a in actions],
    }


def create_onboarding(db: Session, form, actor: User):
    allowed = set(DEPARTMENT_GROUPS[form.department])
    if any(g not in allowed for g in form.required_groups):
        raise HTTPException(422, 'Requested groups exceed approved department access')
    groups = list(dict.fromkeys([DEPARTMENT_GROUPS[form.department][0], *form.required_groups]))
    employee = Employee(full_name=form.full_name, department=form.department, job_title=form.job_title,
                        manager_name=form.manager_name, start_date=form.start_date,
                        work_email='pending@invalid.example', ad_username='pending', status='Prepared')
    db.add(employee)
    db.flush()
    employee.ad_username = f'nc{employee.id:06d}'
    employee.work_email = f'{employee.ad_username}@northstar.example'
    onboard = OnboardingRequest(employee_id=employee.id, requested_by=actor.id,
                                requested_groups_json=json.dumps(groups),
                                device_requirements_json=json.dumps(form.device_requirements), status='Prepared')
    db.add(onboard)
    db.flush()
    record(db, employee.id, 'VALIDATE', employee.work_email, 'Mocked', 'Validated identity, department and least-privilege groups', onboard_id=onboard.id)
    record(db, employee.id, 'AD_CREATE', employee.ad_username, 'Prepared', 'PowerShell lab plan generated; no AD changes', onboard_id=onboard.id)
    for group in groups:
        record(db, employee.id, 'AD_GROUP', group, 'Prepared', 'Group assignment prepared for lab review', onboard_id=onboard.id)
    # Mock external Google operations are never persisted to real services.
    google = MockDirectory()
    first, last = employee.full_name.split(' ', 1)
    google.create_user(employee.work_email, first, last)
    google.assign_group(employee.work_email, GOOGLE_GROUPS[employee.department])
    record(db, employee.id, 'GOOGLE_CREATE', employee.work_email, 'Mocked', 'Google Directory mock create succeeded (not a real account)', onboard_id=onboard.id)
    record(db, employee.id, 'GOOGLE_GROUP', GOOGLE_GROUPS[employee.department], 'Mocked', 'Google group membership simulated', onboard_id=onboard.id)
    if 'Laptop' in form.device_requirements:
        # SQL Server locks the selected row through UPDATE; concurrent reservations
        # cannot both transition the asset from Available to Reserved.
        choices = db.scalars(select(Asset).where(Asset.device_type == 'Laptop', Asset.status == 'Available')
                             .order_by(Asset.id)).all()
        reserved = None
        for candidate in choices:
            result = db.execute(update(Asset).where(Asset.id == candidate.id, Asset.status == 'Available')
                                .values(status='Reserved').execution_options(synchronize_session=False))
            if result.rowcount == 1:
                reserved = candidate
                break
        if reserved:
            db.add(AssetReservation(asset_id=reserved.id, employee_id=employee.id,
                                    onboarding_request_id=onboard.id, status='Reserved'))
            record(db, employee.id, 'LAPTOP_RESERVE', reserved.asset_tag, 'Mocked',
                   'Reserved in existing Task 2 inventory; not physically issued', onboard_id=onboard.id)
            log_event(db, 'ASSET_RESERVED', actor, employee_id=employee.id, asset_id=reserved.id)
        else:
            onboard.status = 'Attention'
            record(db, employee.id, 'LAPTOP_RESERVE', 'Laptop', 'Failed',
                   'No Available laptop; assign stock and retry via new request policy', onboard_id=onboard.id)
    else:
        record(db, employee.id, 'DEVICE_CHECK', 'None', 'Prepared', 'No laptop requested', onboard_id=onboard.id)
    for device in form.device_requirements:
        if device != 'Laptop':
            record(db, employee.id, 'DEVICE_REQUEST', device, 'ManualRequired',
                   'Manual issue required; inventory does not track this device category', onboard_id=onboard.id)
    log_event(db, 'EMPLOYEE_CREATED', actor, employee_id=employee.id)
    log_event(db, 'ONBOARDING_PREPARED', actor, employee_id=employee.id, onboarding_id=onboard.id)
    db.commit()
    return employee_dict(db, employee)


def activate(db: Session, employee: Employee, actor: User):
    onboard = db.scalar(select(OnboardingRequest).where(OnboardingRequest.employee_id == employee.id))
    if not onboard or employee.status != 'Prepared' or onboard.status != 'Prepared':
        raise HTTPException(409, 'Onboarding is not fully prepared or is already activated')
    employee.status = 'Active'  # SIMULATED local lifecycle; no remote AD/Google changes
    onboard.status = 'Activated'
    onboard.activated_at = utc_now()
    log_event(db, 'EMPLOYEE_ACTIVATED', actor, employee_id=employee.id, mode='mock')
    db.commit()
    return employee_dict(db, employee)


def request_offboarding(db: Session, employee: Employee, form, actor: User):
    if employee.status not in ('Active', 'Prepared'):
        raise HTTPException(409, 'Employee not eligible for offboarding')
    prior = db.scalar(select(OffboardingRequest).where(OffboardingRequest.employee_id == employee.id,
                     OffboardingRequest.status.in_(['PendingApproval','Approved','Completed'])))
    if prior:
        raise HTTPException(409, 'Offboarding already requested for this employee')
    item = OffboardingRequest(employee_id=employee.id, requested_by=actor.id,
                              last_working_date=form.last_working_date, reason=form.reason,
                              status='PendingApproval')
    db.add(item)
    db.flush()
    record(db, employee.id, 'REQUEST_APPROVAL', 'Admin reviewer', 'Prepared',
           'Waiting for a different administrator to approve', offboard_id=item.id)
    log_event(db, 'OFFBOARDING_REQUESTED', actor, employee_id=employee.id, offboarding_id=item.id)
    db.commit()
    return item


def approve_offboarding(db: Session, item: OffboardingRequest, actor: User, comment: str):
    if item.status != 'PendingApproval':
        raise HTTPException(409, 'Request is not pending approval')
    if item.requested_by == actor.id:
        raise HTTPException(403, 'Second-person approval required; requester cannot approve')
    employee = db.get(Employee, item.employee_id)
    item.status = 'Approved'
    item.approved_by = actor.id
    item.approved_at = utc_now()
    db.add(ApprovalRecord(offboarding_request_id=item.id, approver_user_id=actor.id,
                          decision='Approved', comment=comment))
    log_event(db, 'OFFBOARDING_APPROVED', actor, employee_id=employee.id, offboarding_id=item.id)
    # All actions below are MOCK/PREPARED. No live AD or Google calls.
    record(db, employee.id, 'AD_DISABLE', employee.ad_username, 'Prepared',
           'Disable-ADAccount plan only; no live directory connection', offboard_id=item.id)
    record(db, employee.id, 'AD_REVOKE_GROUPS', employee.ad_username, 'Prepared',
           'Flag access groups for removal after directory administrator review', offboard_id=item.id)
    google = MockDirectory()
    first, last = employee.full_name.split(' ', 1)
    google.create_user(employee.work_email, first, last)
    google.suspend_user(employee.work_email)
    record(db, employee.id, 'GOOGLE_SUSPEND', employee.work_email, 'Mocked',
           'Mock suspended=True; real Google account unaffected', offboard_id=item.id)
    record(db, employee.id, 'GOOGLE_REVOKE_GROUPS', GOOGLE_GROUPS[employee.department], 'Prepared',
           'Flagged for group review; membership not deleted', offboard_id=item.id)
    reservations = db.scalars(select(AssetReservation).where(
        AssetReservation.employee_id == employee.id, AssetReservation.status == 'Reserved')).all()
    for reservation in reservations:
        result = db.execute(update(Asset).where(Asset.id == reservation.asset_id, Asset.status == 'Reserved')
                            .values(status='Available').execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise HTTPException(409, 'Reserved asset changed unexpectedly; approval aborted')
        reservation.status = 'Released'
        reservation.released_at = utc_now()
        record(db, employee.id, 'RESERVATION_RELEASED', reservation.asset.asset_tag,
               'Mocked', 'Laptop reservation released to inventory', offboard_id=item.id)
        log_event(db, 'ASSET_RESERVATION_RELEASED', actor, employee_id=employee.id,
                  asset_id=reservation.asset_id)
    # HR records aren't Task 2 local User rows. Existing issued assets are not
    # silently returned; explicitly flag for the technician to collect.
    record(db, employee.id, 'DEVICE_RETURN', 'Task 2 inventory', 'ManualRequired',
           'Collect equipment; do not automatically mark physically returned', offboard_id=item.id)
    employee.status = 'Offboarded'
    item.status = 'Completed'
    item.completed_at = utc_now()
    log_event(db, 'OFFBOARDING_COMPLETED', actor, employee_id=employee.id,
              offboarding_id=item.id, mode='mock')
    db.commit()
    return item


def ad_plan(employee: Employee, db: Session):
    onboard = db.scalar(select(OnboardingRequest).where(OnboardingRequest.employee_id == employee.id))
    if not onboard:
        raise HTTPException(404, 'Onboarding request missing')
    return {'mode': 'DryRun', 'samAccountName': employee.ad_username,
            'name': employee.full_name, 'email': employee.work_email,
            'department': employee.department, 'title': employee.job_title,
            'manager': employee.manager_name, 'groups': json.loads(onboard.requested_groups_json),
            'domain': 'northstar.lab', 'operation': 'PrepareAccount'}
