"""Validated single-value formatting only; no Jinja evaluation or email delivery."""
from string import Formatter
from fastapi import HTTPException
from sqlalchemy import select
from app.models import CommunicationTemplate, Claim, ClaimCRMState, utc_now

ALLOWED = {'claim_id','claimant_name','claim_type','claim_status','handler','submission_date'}
DEFAULTS = {
  'acknowledgement': ('We received claim {claim_id}', 'Hello {claimant_name}, we have received your {claim_type} claim {claim_id} on {submission_date}.'),
  'missing_documents': ('Documents required for {claim_id}', 'Hello {claimant_name}, additional documents are needed for claim {claim_id}. Please contact the claims team.'),
  'progress': ('Update on {claim_id}', 'Hello {claimant_name}, claim {claim_id} is now at status {claim_status}. Assigned handler: {handler}.'),
  'completion': ('Claim {claim_id} completed', 'Hello {claimant_name}, claim {claim_id} has reached the {claim_status} stage.'),
}


def validate_template(text):
    if not isinstance(text, str) or not 1 <= len(text) <= 4000:
        raise HTTPException(422, 'Template text length must be 1–4000')
    try:
        for _literal, field, spec, conversion in Formatter().parse(text):
            if field is not None and (field not in ALLOWED or spec or conversion):
                raise HTTPException(422, 'Only predefined simple placeholders are permitted')
    except ValueError:
        raise HTTPException(422, 'Malformed placeholder syntax') from None
    return text


def seed_templates(db):
    for kind, (subject, body) in DEFAULTS.items():
        if not db.scalar(select(CommunicationTemplate.id).where(CommunicationTemplate.kind == kind)):
            db.add(CommunicationTemplate(kind=kind, subject=subject, body=body))
    db.commit()


def preview(template, claim, state):
    variables = {'claim_id':claim.claim_id, 'claimant_name':claim.claimant_name,
                 'claim_type':claim.claim_type, 'claim_status':state.stage if state else claim.status,
                 'handler':(state.assigned_handler if state else None) or 'Claims Team',
                 'submission_date':claim.reported_date.isoformat()}
    return {'kind':template.kind, 'subject':validate_template(template.subject).format_map(variables),
            'body':validate_template(template.body).format_map(variables), 'sent':False}
