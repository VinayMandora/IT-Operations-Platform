# Task 3 architecture — employee joiners and leavers

This is **an extension of Task 1/Task 2**, not a new application. The existing `app/db.py`, Task 1 claims pipelines, Task 2 `User`, `Asset`, `Ticket`, authentication and audit log are reused without recreating tables. The **latest Task 2 login/session fix is preserved**.

## Safety boundary

- All FastAPI onboarding/offboarding routes call only `MockDirectory` and create **AD plans**; none imports or calls real Active Directory cmdlets or live Google credentials. Local HR employee status `Active`/`Offboarded` means *simulated lifecycle*, not live directory state.
- PowerShell `powershell/Invoke-NorthstarAD.ps1` is dry-run by default (requires no domain or RSAT). Its separate `-LabLive` mode requires an isolated Windows Server lab; actual changes additionally require `-CommitLabChanges`, `NORTHSTAR_AD_LAB_ALLOWED=YES` and a typed confirmation.
- `RealGoogleDirectory` exists only in `app/services/google_directory.py` and is used only by **standalone** `scripts/google_workspace_lab.py`, never included by the web application. It requires explicit lab opt-in, a service account file OUTSIDE the repository, delegated administrator and the two Directory scopes. Its targets are constrained to a configured allowed lab domain.
- These are portfolio demonstration controls, not a production employee-identity platform. A production design needs enterprise HR identity matching, a durable outbox/worker for external operations, secret management, full approvals, reconciliation and lifecycle retries.

## Component routing

```text
Browser /employees
  -> app/routers/employee_pages.py -> app/templates/employees.html
    -> app/static/app.js requestJSON() -> /api/employees/*
      -> app/routers/employees.py (RBAC, CSRF, Pydantic)
         -> app/services/employee_service.py (atomic SQLAlchemy changes)
             -> employees / onboarding_requests / offboarding_requests
             -> provisioning_actions / approval_records / asset_reservations
             -> Task 2 assets / Task 2 users / original audit_events
         -> app/services/google_directory.py (MOCK ONLY)

Separate tools (NEVER invoked by API):
  powershell/Invoke-NorthstarAD.ps1        -> dry-run OR isolated AD lab
  scripts/google_workspace_lab.py         -> mock OR explicit Google lab
```

## Model fields and relationships

| Table | Purpose | Integrity |
|---|---|---|
| `employees` | HR record, names, manager, department, start date, generated email/AD name, demo status | Unique email/AD username, department/status CHECKs |
| `onboarding_requests` | Admin request, group/device JSON, preparation state and activation time | Employee and requester FKs; unique onboarding per employee |
| `offboarding_requests` | Technician/Admin departure request, departure date, reason, separate approver, workflow timestamps | Employee and two user FKs; status CHECK |
| `provisioning_actions` | Every mock/prepared/failed/manual-required checklist item, target and result | Parent-request exclusive-or CHECK, employee and request FKs, status CHECK |
| `approval_records` | Approver, rationale, timestamp | Unique offboarding request, approver FK, decision CHECK |
| `asset_reservations` | Reserved Task 2 laptop link to HR employee and onboarding | Filtered unique indexes on active asset and onboarding reservation; CHECK |
| `assets` (modified) | Task 2 asset with additional `Reserved` status | Task 2 assignment allows only `Available`; conditional status update atomically reserves |
| `audit_events` (modified) | Task 1/2/3 event stream | New event types in one extended SQL CHECK; existing rows untouched |

Note: `Employee` is a simulated HR record distinct from existing Task 2 `User` login accounts. This intentionally avoids granting portal accounts just because an external account has been *prepared*. Device reservations are **not** physical issue/return. The offboarding checklist flags outstanding equipment returns instead of falsely marking a device as collected.

## Function-level reference

- `employee_schemas.OnboardIn`: strict name, department, date, group and device validation; duplicate options rejected.
- `employee_schemas.OffboardIn` / `ApprovalIn`: validates reason/date and requires explicit `confirm: true`.
- `employee_service.create_onboarding`: verifies a department group allowlist, persists employee/request/checklist, prepares AD user/groups, simulates Google create/group, reserves an available laptop with a conditional SQL UPDATE, audits and commits. A stock shortage is persisted as `Failed`/`Attention`, not silently ignored.
- `employee_service.activate`: Admin marks the **local simulation** Active only for fully prepared requests; audit is recorded.
- `employee_service.request_offboarding`: creates `PendingApproval`, blocks duplicate pending/completed requests, audits and commits **without changing accounts**.
- `employee_service.approve_offboarding`: requires another Admin, inserts unique approval record, prepares AD disable/group review, simulates Google suspension, releases reservations atomically, flags physical device returns, writes audit and commits.
- `employee_service.ad_plan`: serialises the approved AD-lab plan with allowlisted groups, no credentials.
- `employee_service.employee_dict`: serialises linked checklist and current reservation for API/dashboard.
- `google_directory.MockDirectory`: implements create/list/group/update/suspend entirely in process; no network.
- `google_directory.RealGoogleDirectory`: uses the Google client library and domain-wide delegated service-account credentials **only** when standalone lab configuration is explicitly enabled.
- `routers.employees`: RBAC and CSRF-protected create/read/activate/offboarding/approval/AD-plan routes; only Admin can provision or approve, Technicians can request offboarding, employees have no HR data access.
- `routers.employee_pages.index`: serves combined HR statistics, provisioning actions, reservation counts and approval queue for Admin/Technician.
- `scripts.migrate_task3`: executes SQL Server migration in batches; SQL script owns its transaction.
- `scripts.seed_task3`: adds a second fictional Admin reviewer only if missing.

## Intentional limitations

- Group removal at departure is **flagged for human review**; no destructive delete operations in the demo.
- Reservations are distinct from *issuing* a laptop to a Task 2 `User`. A real joiner would later need a mapped portal account, asset handover acknowledgement, and an explicit `Reserved -> Assigned` transaction with local user link.
- There is no retry scheduler or external event reconciliation because all web operations are mocks. Provisioning actions provide the persistent plan and error trail to extend with a future approval-gated background worker.
- The SQL Server migration is provided for your own SSMS/SQL Express validation. Automated tests use SQLite to remain usable without AD, Workspace or SQL Server.
