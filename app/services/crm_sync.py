"""CRM pull/push operations with per-operation idempotency and durable failure records."""
import json
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Claim, ClaimCRMState, CRMOperation, utc_now
from app.services.claims_workflow import audit, state_for
from app.services.zoho_client import CRMError

REMOTE_STAGES = {
    'Open': 'New', 'Assigned': 'Assigned', 'Evidence Required': 'Evidence Required',
    'Ready for Review': 'Ready for Review', 'Resolved': 'Resolved', 'Closed': 'Resolved',
}


def run_sync(db: Session, claim_reference: str, operation: str, operation_key: str, actor_id: int,
             client, existing=None):
    claim = db.scalar(select(Claim).where(Claim.claim_id == claim_reference))
    if not claim:
        raise HTTPException(404, 'Claim not found')
    prior = existing or db.scalar(select(CRMOperation).where(CRMOperation.operation_key == operation_key))
    if prior and (prior.claim_id != claim.id or prior.operation != operation):
        raise HTTPException(409, 'Operation key already belongs to another request')
    if prior and prior.status == 'Success':
        return {'operation_id': prior.id, 'status': 'Success', 'replayed': True}
    if prior and not existing:
        return {'operation_id': prior.id, 'status': 'Failed', 'replayed': True,
                'retry_count': prior.retry_count, 'error': prior.error_reason}
    state = state_for(db, claim)
    op = prior or CRMOperation(operation_key=operation_key, claim_id=claim.id,
            operation=operation, payload_json=json.dumps({'reference': claim_reference}),
            status='Failed', retry_count=0)
    if not prior:
        db.add(op)
        db.flush()
    elif op.retry_count >= 3:
        raise HTTPException(409, 'Maximum CRM retries reached')
    else:
        op.retry_count += 1
    try:
        if operation == 'pull':
            records = client.list_claims()
            matching = [r for r in records if str(r.get('Claim_Reference')) == claim.claim_id]
            if len(matching) != 1:
                raise CRMError('CRM record not uniquely matched to local claim')
            remote = client.get_claim(str(matching[0]['id']))
            stage = REMOTE_STAGES.get(remote.get('Status'))
            if not stage:
                raise CRMError('CRM status mapping not configured for this record')
            remote_id = str(remote['id'])
            collision = db.scalar(select(ClaimCRMState).where(ClaimCRMState.zoho_record_id == remote_id,
                                                            ClaimCRMState.claim_id != claim.id))
            if collision:
                raise CRMError('CRM record is already linked to another claim')
            state.zoho_record_id = remote_id
            state.stage = stage
            state.missing_documents = stage == 'Evidence Required' or remote.get('Missing_Documents') is True
            if stage == 'Resolved':
                state.completed_at = state.completed_at or utc_now()
            if stage in {'Evidence Required', 'Ready for Review'}:
                claim.status = 'In Progress'
            elif stage == 'Resolved':
                claim.status = 'Closed'
        elif operation == 'push':
            if not state.zoho_record_id:
                raise CRMError('Link CRM record via pull before pushing')
            client.update_status(state.zoho_record_id, state.stage)
        else:
            raise CRMError('Unsupported CRM operation')
        state.integration_status = 'Synced'
        state.last_updated = utc_now()
        state.synced_at = utc_now()
        op.status = 'Success'
        op.error_reason = None
        audit(db, 'CLAIM_CRM_SYNC', actor_id, claim_id=claim_reference, operation=operation)
    except CRMError as exc:
        state.integration_status = 'Failed'
        op.status = 'Failed'
        op.error_reason = str(exc)[:1000]
    op.finished_at = utc_now()
    db.commit()
    return {'operation_id': op.id, 'status': op.status, 'replayed': False,
            'error': op.error_reason, 'retry_count': op.retry_count,
            'retryable': op.status == 'Failed' and op.retry_count < 3}


def retry_sync(db, operation_id: int, actor_id: int, client):
    op = db.get(CRMOperation, operation_id)
    if not op:
        raise HTTPException(404, 'CRM operation not found')
    if op.status != 'Failed':
        raise HTTPException(409, 'Only failed CRM operations may be retried')
    claim = db.get(Claim, op.claim_id)
    return run_sync(db, claim.claim_id, op.operation, op.operation_key, actor_id, client, existing=op)
