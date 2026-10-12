"""Task 4 pages reuse Task 2/3 session, CSRF and Jinja2 layout."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Claim, ClaimCRMState, CommunicationTemplate, WorkflowExecution, WorkflowRule
from app.routers.pages import render
from app.security import require_roles

router = APIRouter(tags=['claims workflow browser'])


@router.get('/claims-management')
def claims_dashboard(request: Request, db: Session = Depends(get_db),
                     _user=Depends(require_roles('Admin'))):
    rows = db.execute(select(Claim, ClaimCRMState).outerjoin(ClaimCRMState,
                        ClaimCRMState.claim_id == Claim.id).order_by(Claim.id.desc()).limit(100)).all()
    from app.services.claims_workflow import claim_details
    return render(request, 'claims_management.html', db,
                  claims=[claim_details(c,s) for c,s in rows])


@router.get('/workflow-logs')
def workflow_page(request: Request, db: Session = Depends(get_db),
                  _user=Depends(require_roles('Admin'))):
    rows = db.scalars(select(WorkflowExecution).order_by(WorkflowExecution.id.desc()).limit(200)).all()
    return render(request, 'workflow_logs.html', db, executions=rows,
                  rules=db.scalars(select(WorkflowRule).order_by(WorkflowRule.id)).all())


@router.get('/communication-templates')
def templates_page(request: Request, db: Session = Depends(get_db),
                   _user=Depends(require_roles('Admin'))):
    rows = db.scalars(select(CommunicationTemplate).order_by(CommunicationTemplate.kind)).all()
    return render(request, 'communication_templates.html', db, templates=rows)
