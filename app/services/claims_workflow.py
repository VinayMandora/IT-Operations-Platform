"""Task 4 transactional workflows over original claims; no change to Task 1 schema."""
import json
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (AuditEvent, Claim, ClaimCRMState, Ticket, TicketHistory,
                        WorkflowRule, WorkflowExecution, WorkflowTransition, utc_now)

STAGES = ('New', 'Assigned', 'Evidence Required', 'Ready for Review', 'Resolved')
EVENTS = ('submitted','missing_documents','evidence_received','resolved')
ACTIONS = ('assign_team','evidence_required','ready_for_review','resolve','demo_fail')
RULES = (
    ('Assign new claim to claims team','submitted','assign_team',{'handler': 'Claims Team'}),
    ('Request missing evidence','missing_documents','evidence_required',{}),
    ('Evidence arrived','evidence_received','ready_for_review',{}),
    ('Complete claim','resolved','resolve',{}),
)


def audit(db, event, actor_id, **details):
    db.add(AuditEvent(event_type=event, actor_user_id=actor_id,
                      details_json=json.dumps(details, ensure_ascii=False, default=str)))


def seed_rules(db: Session):
    for name, event, action, params in RULES:
        if not db.scalar(select(WorkflowRule.id).where(WorkflowRule.name == name)):
            db.add(WorkflowRule(name=name, event_type=event, action_type=action,
                                parameters_json=json.dumps(params), enabled=True))
    db.commit()


def state_for(db, claim):
    state = db.scalar(select(ClaimCRMState).where(ClaimCRMState.claim_id == claim.id))
    if state is None:
        state = ClaimCRMState(claim_id=claim.id, stage='New', missing_documents=False,
                              integration_status='Not Synced', last_updated=utc_now())
        db.add(state)
        db.flush()
    return state


def claim_details(claim, state):
    return {
        'claim_id': claim.claim_id, 'claimant_name': claim.claimant_name,
        'claim_type': claim.claim_type, 'claim_status': claim.status,
        'handler': state.assigned_handler if state else None,
        'submission_date': claim.reported_date.isoformat(),
        'missing_documentation': state.missing_documents if state else False,
        'stage': state.stage if state else 'New',
        'last_update': state.last_updated.isoformat() + 'Z' if state else claim.created_at.isoformat() + 'Z',
        'integration_status': state.integration_status if state else 'Not Synced',
        'zoho_record_id': state.zoho_record_id if state else None,
        'completed_at': state.completed_at.isoformat() + 'Z' if state and state.completed_at else None,
        'amount_gbp': str(claim.amount_gbp),
    }


def _apply(claim, state, rule):
    before = state.stage
    params = json.loads(rule.parameters_json)
    if rule.action_type == 'demo_fail':
        raise ValueError('Demonstration validation failure: check the configured workflow action')
    if rule.action_type == 'assign_team':
        if before != 'New':
            raise ValueError('Only new claims can be assigned')
        handler = params.get('handler', 'Claims Team')
        if not isinstance(handler, str) or not 2 <= len(handler) <= 120:
            raise ValueError('Invalid claims handler')
        state.assigned_handler = handler
        state.stage = 'Assigned'
    elif rule.action_type == 'evidence_required':
        if before not in ('New','Assigned','Ready for Review'):
            raise ValueError('Cannot request evidence in this stage')
        state.missing_documents = True
        state.stage = 'Evidence Required'
        claim.status = 'In Progress'
    elif rule.action_type == 'ready_for_review':
        if before != 'Evidence Required':
            raise ValueError('Evidence was not previously requested')
        state.missing_documents = False
        state.stage = 'Ready for Review'
        claim.status = 'In Progress'
    elif rule.action_type == 'resolve':
        if before not in ('Ready for Review','Assigned') or state.missing_documents:
            raise ValueError('Resolve only after required evidence is supplied')
        state.stage = 'Resolved'
        claim.status = 'Closed'
        state.completed_at = utc_now()
    else:
        raise ValueError('Unsupported action')
    state.last_updated = utc_now()
    return before, state.stage


def _failure_ticket(db, actor_id, claim, reason):
    now = utc_now()
    ticket = Ticket(employee_id=actor_id, title=f'Claims workflow failed: {claim.claim_id}',
                    description=f'Workflow action failed for {claim.claim_id}: {reason[:600]}',
                    category='Software', priority='High', status='Open', created_at=now,
                    sla_due_at=now + timedelta(hours=8))
    db.add(ticket)
    db.flush()
    db.add(TicketHistory(ticket_id=ticket.id, actor_user_id=actor_id, action='Created',
                         note='Automatically opened by Task 4 workflow engine', new_status='Open'))
    audit(db, 'TICKET_CREATED', actor_id, ticket_id=ticket.id, source='claims_workflow')
    return ticket.id


def _execute_rule(db, claim, state, rule, event_key, actor_id, existing=None):
    if existing and existing.status == 'Success':
        return {'execution_id': existing.id, 'status': 'Success', 'replayed': True}
    execution = existing or WorkflowExecution(claim_id=claim.id, rule_id=rule.id,
                event_key=event_key, status='Failed', input_status=state.stage,
                retry_count=0, started_at=utc_now())
    if not existing:
        db.add(execution)
        db.flush()
    else:
        if execution.retry_count >= 3:
            raise HTTPException(409, 'Maximum retry count reached')
        execution.retry_count += 1
    execution.started_at = utc_now()
    execution.input_status = state.stage
    try:
        # All validations in _apply run before any substantive change for each action.
        previous, current = _apply(claim, state, rule)
        execution.status = 'Success'
        execution.output_status = current
        execution.error_reason = None
        db.add(WorkflowTransition(execution_id=execution.id, claim_id=claim.id,
                                  from_stage=previous, to_stage=current))
        audit(db, 'CLAIM_WORKFLOW', actor_id, claim_id=claim.claim_id,
              workflow=rule.name, before=previous, after=current)
    except (ValueError, TypeError) as error:
        # Do not persist secrets or exception tracebacks in database or UI.
        execution.status = 'Failed'
        execution.output_status = state.stage
        execution.error_reason = str(error)[:1000]
        if not execution.support_ticket_id:
            execution.support_ticket_id = _failure_ticket(db, actor_id, claim, str(error))
        audit(db, 'CLAIM_WORKFLOW_FAILED', actor_id, claim_id=claim.claim_id,
              workflow=rule.name, execution_id=execution.id)
    execution.finished_at = utc_now()
    return {'execution_id': execution.id, 'status': execution.status,
            'replayed': False, 'input_status': execution.input_status,
            'output_status': execution.output_status, 'error': execution.error_reason,
            'support_ticket_id': execution.support_ticket_id,
            'retry_count': execution.retry_count}


def process_event(db, claim_reference: str, event_type: str, event_key: str, actor_id: int):
    claim = db.scalar(select(Claim).where(Claim.claim_id == claim_reference))
    if not claim:
        raise HTTPException(404, 'Claim not found')
    rules = db.scalars(select(WorkflowRule).where(WorkflowRule.event_type == event_type,
                            WorkflowRule.enabled.is_(True)).order_by(WorkflowRule.id)).all()
    if not rules:
        raise HTTPException(409, 'No enabled workflow rule for this event')
    state = state_for(db, claim)
    results = []
    for rule in rules:
        previous = db.scalar(select(WorkflowExecution).where(
            WorkflowExecution.claim_id == claim.id, WorkflowExecution.rule_id == rule.id,
            WorkflowExecution.event_key == event_key))
        if previous:
            results.append({'execution_id': previous.id, 'status': previous.status,
                            'replayed': True, 'retry_count': previous.retry_count})
        else:
            results.append(_execute_rule(db, claim, state, rule, event_key, actor_id))
    db.commit()
    return {'claim_id': claim_reference, 'event_type': event_type, 'results': results}


def retry_execution(db, execution_id: int, actor_id: int):
    exe = db.get(WorkflowExecution, execution_id)
    if not exe:
        raise HTTPException(404, 'Execution not found')
    if exe.status != 'Failed':
        raise HTTPException(409, 'Only failed workflows can be retried')
    claim = db.get(Claim, exe.claim_id)
    state = state_for(db, claim)
    result = _execute_rule(db, claim, state, exe.rule, exe.event_key, actor_id, existing=exe)
    db.commit()
    return result
