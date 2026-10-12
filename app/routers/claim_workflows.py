"""Workflow rules, idempotent events, admin retry, and safe preview-only templates."""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import (Claim, ClaimCRMState, CommunicationTemplate, User,
                        WorkflowExecution, WorkflowRule, WorkflowTransition, utc_now)
from app.security import require_roles
from app.services.claims_workflow import audit, process_event, retry_execution
from app.services.claim_templates import DEFAULTS, preview, validate_template
from app.workflow_schemas import RuleIn, RulePatch, TemplateUpdate, WorkflowEventIn

router = APIRouter(prefix='/api/workflows', tags=['claims workflow automation'])


@router.get('/rules')
def rules(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin'))):
    rows = db.scalars(select(WorkflowRule).order_by(WorkflowRule.id)).all()
    return {'items':[{'id':r.id,'name':r.name,'event_type':r.event_type,
                      'action_type':r.action_type,'parameters':json.loads(r.parameters_json),
                      'enabled':r.enabled} for r in rows]}


@router.post('/rules', status_code=201)
def add_rule(body: RuleIn, db: Session = Depends(get_db),
             _user: User = Depends(require_roles('Admin'))):
    if db.scalar(select(WorkflowRule.id).where(WorkflowRule.name == body.name)):
        raise HTTPException(409, 'Rule name is already in use')
    row = WorkflowRule(name=body.name, event_type=body.event_type, action_type=body.action_type,
                       parameters_json=json.dumps({'handler': body.handler or 'Claims Team'}
                                                   if body.action_type == 'assign_team' else {}), enabled=True)
    db.add(row)
    db.commit()
    return {'id':row.id,'name':row.name}


@router.patch('/rules/{rule_id}')
def toggle_rule(rule_id: int, body: RulePatch, db: Session = Depends(get_db),
                _user: User = Depends(require_roles('Admin'))):
    rule = db.get(WorkflowRule, rule_id)
    if not rule:
        raise HTTPException(404, 'Rule not found')
    if not body.model_fields_set:
        raise HTTPException(422, 'Provide at least one rule change')
    if body.enabled is not None:
        rule.enabled = body.enabled
    if body.action_type is not None:
        rule.action_type = body.action_type
    if body.handler is not None or body.action_type == 'assign_team':
        rule.parameters_json = json.dumps({'handler': body.handler or 'Claims Team'})
    db.commit()
    return {'id':rule.id,'enabled':rule.enabled,'action_type':rule.action_type}


@router.post('/events')
def trigger(body: WorkflowEventIn, db: Session = Depends(get_db),
            user: User = Depends(require_roles('Admin'))):
    return process_event(db, body.claim_id, body.event_type, body.event_key, user.id)


@router.get('/executions')
def executions(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin'))):
    items = db.scalars(select(WorkflowExecution).order_by(WorkflowExecution.id.desc()).limit(250)).all()
    return {'items': [{'id':e.id, 'workflow':e.rule.name, 'claim_id':e.claim.claim_id,
            'timestamp':e.started_at.isoformat()+'Z', 'input_status':e.input_status,
            'output_status':e.output_status, 'status':e.status,
            'error':e.error_reason,'retry_count':e.retry_count,
            'support_ticket_id':e.support_ticket_id} for e in items]}


@router.post('/executions/{execution_id}/retry')
def retry(execution_id: int, db: Session = Depends(get_db),
          user: User = Depends(require_roles('Admin'))):
    return retry_execution(db, execution_id, user.id)


@router.get('/transitions')
def transitions(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin'))):
    rows = db.scalars(select(WorkflowTransition).order_by(WorkflowTransition.id.desc()).limit(200)).all()
    return {'items':[{'claim_id':t.claim_id,'from_stage':t.from_stage,
                      'to_stage':t.to_stage,'occurred_at':t.occurred_at.isoformat()+'Z'} for t in rows]}


@router.get('/templates')
def templates(db: Session = Depends(get_db), _user: User = Depends(require_roles('Admin'))):
    return {'items':[{'kind':t.kind,'subject':t.subject,'body':t.body} for t in
                     db.scalars(select(CommunicationTemplate).order_by(CommunicationTemplate.kind)).all()]}


@router.put('/templates/{kind}')
def update_template(kind: str, body: TemplateUpdate, db: Session = Depends(get_db),
                    user: User = Depends(require_roles('Admin'))):
    if kind not in DEFAULTS:
        raise HTTPException(404, 'Unknown template type')
    record = db.scalar(select(CommunicationTemplate).where(CommunicationTemplate.kind == kind))
    if not record:
        raise HTTPException(404, 'Seed the communication templates first')
    record.subject = validate_template(body.subject)
    record.body = validate_template(body.body)
    record.updated_by = user.id
    record.updated_at = utc_now()
    audit(db, 'CLAIM_TEMPLATE_UPDATED', user.id, kind=kind)
    db.commit()
    return {'kind':kind, 'updated':True}


@router.get('/templates/{kind}/preview/{reference}')
def template_preview(kind: str, reference: str, db: Session = Depends(get_db),
                     _user: User = Depends(require_roles('Admin'))):
    template = db.scalar(select(CommunicationTemplate).where(CommunicationTemplate.kind == kind))
    claim = db.scalar(select(Claim).where(Claim.claim_id == reference))
    if not template or not claim:
        raise HTTPException(404, 'Template or claim not found')
    state = db.scalar(select(ClaimCRMState).where(ClaimCRMState.claim_id == claim.id))
    return preview(template, claim, state)
