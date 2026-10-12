"""Role-protected task 4 claims dashboard and CRM sync endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Claim, ClaimCRMState, CRMOperation, User
from app.security import require_roles
from app.services.claims_workflow import claim_details
from app.services.crm_sync import retry_sync, run_sync
from app.services.zoho_client import CRMError, make_client
from app.workflow_schemas import SyncIn

router = APIRouter(prefix='/api/crm', tags=['claims CRM integration'])


def get_zoho():
    return make_client()


@router.get('/claims')
def claims_list(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                stage: str | None = None, db: Session = Depends(get_db),
                _user: User = Depends(require_roles('Admin'))):
    statement = select(Claim, ClaimCRMState).outerjoin(ClaimCRMState, ClaimCRMState.claim_id == Claim.id)
    if stage:
        statement = statement.where(ClaimCRMState.stage == stage)
    rows = db.execute(statement.order_by(Claim.id.desc()).offset(offset).limit(limit)).all()
    return {'items':[claim_details(c,s) for c,s in rows], 'count':len(rows), 'limit':limit, 'offset':offset}


@router.get('/claims/{reference}')
def claims_detail(reference: str, db: Session = Depends(get_db),
                  _user: User = Depends(require_roles('Admin'))):
    row = db.execute(select(Claim, ClaimCRMState).outerjoin(ClaimCRMState,
                     ClaimCRMState.claim_id == Claim.id).where(Claim.claim_id == reference)).first()
    if not row:
        raise HTTPException(404, 'Claim not found')
    return claim_details(*row)


@router.get('/remote')
def remote_list(_user: User = Depends(require_roles('Admin')), client=Depends(get_zoho)):
    try:
        return {'items': client.list_claims()}
    except CRMError as exc:
        raise HTTPException(503 if exc.retryable else 422, str(exc)) from None


@router.get('/remote/{record_id}')
def remote_one(record_id: str, _user: User = Depends(require_roles('Admin')),
               client=Depends(get_zoho)):
    try:
        return client.get_claim(record_id)
    except CRMError as exc:
        raise HTTPException(503 if exc.retryable else 404, str(exc)) from None


@router.post('/claims/{reference}/sync')
def pull(reference: str, body: SyncIn, db: Session = Depends(get_db),
         user: User = Depends(require_roles('Admin')), client=Depends(get_zoho)):
    return run_sync(db, reference, 'pull', body.operation_key, user.id, client)


@router.post('/claims/{reference}/push')
def push(reference: str, body: SyncIn, db: Session = Depends(get_db),
         user: User = Depends(require_roles('Admin')), client=Depends(get_zoho)):
    return run_sync(db, reference, 'push', body.operation_key, user.id, client)


@router.get('/operations')
def operations(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin'))):
    rows = db.scalars(select(CRMOperation).order_by(CRMOperation.id.desc()).limit(200)).all()
    return {'items':[{'id':v.id,'key':v.operation_key,'operation':v.operation,
                      'status':v.status,'retry_count':v.retry_count,'error':v.error_reason}
                     for v in rows]}


@router.post('/operations/{operation_id}/retry')
def retry(operation_id: int, db: Session = Depends(get_db),
          user: User = Depends(require_roles('Admin')), client=Depends(get_zoho)):
    return retry_sync(db, operation_id, user.id, client)
