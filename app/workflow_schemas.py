"""Validated Task 4 API contracts. No arbitrary Python or SQL action execution."""
from typing import Literal
from pydantic import BaseModel, Field


class WorkflowEventIn(BaseModel):
    claim_id: str = Field(min_length=3, max_length=10)
    event_type: Literal['submitted', 'missing_documents', 'evidence_received', 'resolved']
    event_key: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_:\-]+$')


class RuleIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    event_type: Literal['submitted', 'missing_documents', 'evidence_received', 'resolved']
    action_type: Literal['assign_team', 'evidence_required', 'ready_for_review', 'resolve', 'demo_fail']
    handler: str | None = Field(default=None, max_length=120)


class RulePatch(BaseModel):
    enabled: bool | None = None
    action_type: Literal['assign_team', 'evidence_required', 'ready_for_review', 'resolve', 'demo_fail'] | None = None
    handler: str | None = Field(default=None, min_length=2, max_length=120)


class SyncIn(BaseModel):
    operation_key: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_:\-]+$')


class TemplateUpdate(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
