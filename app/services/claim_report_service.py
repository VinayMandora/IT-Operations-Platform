"""Five-sheet Excel export aligned with Tasks 1/2 openpyxl report implementation."""
from io import BytesIO
from sqlalchemy import select
from sqlalchemy.orm import Session
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from app.models import Claim, ClaimCRMState, WorkflowExecution
from app.services.report_service import excel_safe


def add_sheet(wb, title, headers, data):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for row in data:
        ws.append([excel_safe(str(v)) if isinstance(v, str) else v for v in row])
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='123C5C')
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    for i, header in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = min(38, max(15, len(header) + 4))
    return ws


def build_report(db: Session) -> bytes:
    rows = db.execute(select(Claim, ClaimCRMState).outerjoin(ClaimCRMState,
                     ClaimCRMState.claim_id == Claim.id).order_by(Claim.id)).all()
    executions = db.scalars(select(WorkflowExecution).order_by(WorkflowExecution.id)).all()
    wb = Workbook()
    wb.remove(wb.active)
    add_sheet(wb, 'Claims by Status', ['Reference', 'Claimant', 'Type', 'Stage', 'Original status', 'Handler'],
        [(c.claim_id, c.claimant_name, c.claim_type, s.stage if s else 'New',
          c.status, s.assigned_handler if s else None) for c, s in rows])
    counts = add_sheet(wb, 'Status Summary', ['Workflow stage', 'Claim count'],
        [(name, None) for name in ('New','Assigned','Evidence Required','Ready for Review','Resolved')])
    for rownum in range(2, 7):
        counts.cell(rownum, 2).value = f"=COUNTIF('Claims by Status'!$D$2:$D$100001,A{rownum})"
    add_sheet(wb, 'Missing Documents', ['Reference', 'Claimant', 'Stage', 'Submitted'],
        [(c.claim_id, c.claimant_name, s.stage, c.reported_date)
         for c, s in rows if s and s.missing_documents])
    add_sheet(wb, 'Failed Workflows', ['Reference', 'Workflow', 'Error', 'Retries', 'Created UTC'],
        [(e.claim.claim_id, e.rule.name, e.error_reason, e.retry_count, e.started_at)
         for e in executions if e.status == 'Failed'])
    add_sheet(wb, 'Processing Time', ['Reference', 'Submitted', 'Resolved', 'Days to resolve'],
        [(c.claim_id, c.reported_date, s.completed_at if s else None,
          ((s.completed_at.date() - c.reported_date).days if s and s.completed_at else None))
         for c,s in rows])
    failed_claim_ids = {e.claim_id for e in executions if e.status == 'Failed'}
    add_sheet(wb, 'Intervention', ['Reference','Claimant','Stage','Integration status','Action'],
        [(c.claim_id, c.claimant_name, s.stage, s.integration_status,
          ('Review workflow failure' if c.id in failed_claim_ids else
           'Review failed CRM sync' if s.integration_status == 'Failed' else 'Request evidence'))
         for c,s in rows if s and (s.integration_status == 'Failed' or s.missing_documents or c.id in failed_claim_ids)])
    summary = wb.create_sheet('Summary', 0)
    summary.append(['Northstar Claims Ltd — Task 4 workflow report', 'Value'])
    summary.append(['Total claims', "=COUNTA('Claims by Status'!A2:A100001)"])
    summary.append(['Evidence required', '=COUNTA(\'Missing Documents\'!A2:A100001)'])
    summary.append(['Failed workflows', "=COUNTA('Failed Workflows'!A2:A100001)"])
    summary.append(['Average processing days', '=IFERROR(AVERAGE(\'Processing Time\'!D2:D100001),0)'])
    summary.append(['Requiring intervention', "=COUNTA('Intervention'!A2:A100001)"])
    summary.column_dimensions['A'].width = 48
    summary.column_dimensions['B'].width = 24
    for cell in summary[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='123C5C')
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()
