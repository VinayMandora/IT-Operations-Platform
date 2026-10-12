# Task 4 architecture — additive integration

Task 4 is implemented **in the same project** as Tasks 1–3. The SQL Server database remains `ClaimsITOpsDemo`; authentication comes from `app/security.py`; audit events reuse `app/models.AuditEvent`; on failure the new workflow engine creates a real *local* Task 2 `Ticket` and `TicketHistory`.

## Persistent model relationships

- `claims` (Task 1) → `claim_crm_states` (zero/one): operational workflow stage, handler, document flag, CRM ID, sync timestamps; **existing Task 1 fields and constraints are unchanged**.
- `claims` → `workflow_executions` (many) → `workflow_rules` (one), and optionally → `workflow_transitions` (one success). The database uniqueness on `(claim_id,rule_id,event_key)` prevents replayed events creating a second action.
- `workflow_executions.support_ticket_id` → `tickets.id` (Task 2). Each failed execution gets one support ticket, never a second escalation on retry.
- `claims` → `crm_operations` (many): unique operation keys, outcome, retry count and error; outgoing/incoming CRM changes are explicitly requested.
- `communication_templates`: editable subjects and bodies with allowlisted placeholders; previews only.
- `audit_events`: new Task 4 event types are added to the original existing constraint and records.

## Operations

1. `app/services/claims_workflow.py`: validates allowed status transitions and rule actions; applies changes transactionally; creates transition/execution/audit rows; escalates a rule failure to a helpdesk ticket. Uses **original** claim status mapping (`Open`, `In Progress`, `Closed`) while retaining richer `ClaimCRMState.stage`.
2. `app/services/zoho_client.py`: deterministic `MockZohoClient` plus an explicitly opt-in `RealZohoClient` using V8 endpoint naming, OAuth refresh and configurable regional API host, module and field API names. OAuth client secrets/tokens are environment-only and never placed in log messages. Remote reads are limited to 10 pages of 200 records; production sync for larger modules needs incremental paging.
3. `app/services/crm_sync.py`: correlates remote and local records by claim reference, links a remote record, syncs metadata and maps status; pushes a stage to CRM; logs failure outcomes for manual retry. No automatic, uncontrolled real API requests.
4. `app/services/claim_templates.py`: validates **only** `{claim_id}`, `{claimant_name}`, `{claim_type}`, `{claim_status}`, `{handler}`, `{submission_date}`. No dotted expressions, indexing, conversions or format-spec expressions. No delivery API.
5. `app/services/claim_report_service.py`: follows the existing Python Excel reporter and produces seven worksheets including summary formulas and five requested report views.
6. `app/routers/claims_crm.py`: server-side Admin permission on dashboard data, CRM operations, remote reads and retries.
7. `app/routers/claim_workflows.py`: Admin-only rule configuration, events, logs, failed execution retry, templates, previews.
8. `app/routers/claim_pages.py`: three HTML pages reusing Task 2 sessions and CSRF headers from `app/static/app.js`.

## Idempotency and consistency

- A *client-generated immutable event key* identifies the same event across network retries. A claim/rule/event triplet is unique; a successful or failed event is returned as already processed, and failed executions are only retried using the dedicated Admin endpoint.
- A *client-generated immutable operation key* identifies a CRM pull/push. A result is stored in `crm_operations`; a failed operation can only be retried using the dedicated Admin endpoint, at most three retries.
- Database check constraints, indexes, and foreign keys enforce core invariants on SQL Server and in SQLite test fixtures. Never run `Base.metadata.drop_all()` against the live SQL Server instance.
- In a multi-worker production scenario add explicit database row locks/queueing and scheduler-driven CRM paging; Task 4 is a portfolio **local demonstration**.

## Boundaries

Mock CRM data lives in `sample_data/task4_zoho_mock.json` and is not a real Zoho organisation. Browser template previews never send email. Only SQL Server and Task 2 local helpdesk records are changed by default. Real Zoho access requires *both* `ZOHO_MODE=real` and `ZOHO_REAL_ENABLED=YES`, a supported region, credentials and module/field setup. Run real integration only against an authorised Zoho test/sandbox organisation.
