# Task 2 — implementation and function-level architecture

This document accompanies the complete source document and `README.md`. It explains the functions, their data flow and how to extend the **existing** Task 1 project without rebuilding or dropping tables.

## Data flow

```text
Windows 11 browser (HTML / JS)
    |  signed HttpOnly cookie + X-CSRF-Token
    v
app/main.py -> FastAPI routers
    |  Depends(get_db) and Depends(current_user / require_roles)
    +-> auth.py    -> security.py -> users
    +-> tickets.py -> helpdesk_service.py -> tickets, ticket_history, audit_events
    +-> assets.py  -> asset_service.py    -> assets, asset_movements, audit_events
    +-> pages.py   -> Jinja2 templates
    +-> it_reports.py -> it_report_service.py -> Excel downloads
    +-> original Task 1 claims/imports/reports -> same claims data and existing services
                     |
                     v
              app/db.py -> SQLAlchemy -> pyodbc -> ClaimsITOpsDemo on SQL Server
```

## Database schema, relationships and constraints

| Table | Role | Database-enforced constraints |
| --- | --- | --- |
| `users` | Local accounts for employees, technicians and admins | unique username/email, role CHECK, not-null password hash, active bit. |
| `assets` | Physical inventory and current holder | unique asset tag/serial, device-type and status CHECKs, warranty order CHECK, employee FK, CHECK tying status Assigned to non-null employee. |
| `tickets` | Fault, priority, owner, technician, asset, SLA and timestamps | employee/technician/device FKs, priority/category/status CHECKs, SLA due timestamp, indexes on status/due date and assignee. |
| `ticket_history` | Append-only notes/assignments/status transitions | ticket FK, user FK, timestamp, from/to status, note; indexed by ticket. |
| `asset_movements` | Each assign/return with human initiator | asset FK, employee FK, actor FK, action and UTC timestamp; indexed by asset. |
| `audit_events` | Shared Task 1/Task 2 audit log | Old rows retained; nullable import batch and new nullable actor FK; expanded event-type CHECK. |

Task 1 original tables `claims`, `import_batches` and `rejected_rows` are left untouched. The original `AuditEvent` columns and import code remain compatible: `IMPORT_COMPLETED` rows continue to have `import_batch_id`; Task 2 events instead have `actor_user_id` and structured JSON details.

### Ticket uniqueness and SLA

`Ticket.reference` is a read-only SQLAlchemy property derived from the unique database identity `id`. A ticket created with ID 23 has the stable reference `TKT-000023`; there is no secondary reference sequence that can collide, and the integer ID cannot change. The SLA deadline is set once as `created_at + SLA_HOURS[priority]`. Priority changes aren't implemented because they would alter SLA policy retrospectively. `sla_status()` checks the stored resolution timestamp against the due time and flags unresolved overdue tickets at request time. This is a **demonstration SLA policy**, not a contract.

### Asset concurrency and conflicting assignments

`change_assignment()` executes one conditional SQL `UPDATE`:

- Assign only if `status='Available' AND assigned_employee_id IS NULL`.
- Return only if `status='Assigned' AND assigned_employee_id=<expected-holder>`.
- Exactly one row must change; otherwise return HTTP 409.

SQL Server updates are atomic and take write locks. This prevents two concurrent requests assigning one device to different employees. A database `ck_assets_assignment` CHECK guards the invariant even against writes outside FastAPI. Every successful operation adds one `asset_movements` row and one `AuditEvent` in the same SQLAlchemy transaction. `tickets.assign()` uses a conditional update to make competing technician self-claims fail rather than overwrite one another.

## Function-by-function reference

### Security (`app/security.py`)

- `hash_password(password)`: generates a new salted Argon2id hash. Hashes—not raw passwords—are stored in `users.password_hash`.
- `verify_password(hash_value, password)`: safely checks input passwords against Argon2id hashes, returning `False` on mismatches.
- `signer()`: loads `APP_SECRET_KEY` from the private `.env`; fails closed if the secret is absent or too short. Returns a time-limited signed serializer.
- `create_session(user)`: issues a signed cookie token containing only user ID and a random CSRF token (no password or role claim).
- `cookie_secure()`: controls the cookie's HTTPS `Secure` flag from environment, `false` only for local HTTP.
- `session_data(request)`: validates cookie signature and 8-hour expiry and checks the two required payload fields.
- `current_user(request, db)`: reloads the account from SQL Server on **each** request, checks `is_active`, and verifies `X-CSRF-Token` on non-GET operations.
- `require_roles(*roles)`: dependency factory returning a 403 on disallowed access. Used in both APIs and Jinja browser pages.
- `html_context(request, db)`: exposes only a validated current user and CSRF token to server-rendered pages.

### HTTP validation (`app/schemas.py`)

- `StrictModel`: Pydantic base with forbidden unknown JSON fields and stripped text.
- `UserCreate` and `UserEdit`: password-length and role validation; admin-only POST/PATCH route enforces privilege controls.
- `TicketCreate`, `TicketAssign`, `TicketUpdate` and `TicketNote`: validated issue category, priorities, note size and technician ID. `TicketUpdate` status changes are further checked by the ticket state machine.
- `AssetCreate`: requires asset tag, serial, device type, purchase date and model; the `validate_dates()` model validator blocks future purchase dates and invalid warranty order.
- `AssetEdit`, `AssetAssign`: restrict edited fields and positive employee IDs. Disallow making a device Assigned simply by editing status.
- `clean()`: reusable whitespace normaliser for potential future input cleaning extensions.

### Authentication/account routes (`app/routers/auth.py`)

- `public_user()`: serialises safe account fields; never returns `password_hash`.
- `login()`: validates credentials; sets `nc_session` as HttpOnly, SameSite=Strict cookie and returns a one-time-in-session CSRF token.
- `logout()`: verifies user/CSRF before clearing the browser cookie.
- `me()`: returns current user's public account information.
- `list_users()`: Admin-only listing of accounts.
- `create_user()`: Admin-only creation, Argon2id hashing, unique-field conflict handling, `USER_CREATED` audit.
- `edit_user()`: Admin can update fields and reset passwords while blocking self-deactivation, removing the last Admin, role changes conflicting with assigned devices/tickets and duplicate emails. Writes `USER_UPDATED` audit **without recording password values**.

### Helpdesk router (`app/routers/tickets.py`)

- `ticket_query()`: builds an ORM query with related employee, technician, asset and ticket history preloaded for safe JSON serialisation.
- `create_ticket()`: allows signed-in users to report problems, sets their own identity except Admin submissions on an employee's behalf, checks employee device ownership, generates SLA timestamp, adds the history event and audit in one transaction.
- `list_tickets()`: checks role and scopes employees to own tickets, technicians to own/assigned tickets, and admins to all tickets; supports status/priority filters and pagination.
- `detail()`: fetches a single permitted ticket and its full history; returns 404 rather than leaking other employees' ticket IDs.
- `assign()`: Admin assigns active technicians; technicians only self-claim an unassigned/currently-self-assigned ticket. Conditional SQL UPDATE rejects concurrency conflicts. Records `assigned_at`.
- `update_ticket()`: enforces the state machine, sets resolved/closed timestamps, requires substantive resolution details, and records from/to status with audit.
- `add_note()`: Admin or assigned tech adds a troubleshooting entry; closed tickets are read-only. Creates a ticket-history and audit row without replacing earlier notes.

### Helpdesk services (`app/services/helpdesk_service.py`)

- `SLA_HOURS`: business demonstration dictionary (`Low=72`, `Medium=24`, `High=8`, `Critical=2`).
- `TRANSITIONS`: explicit state machine guarding invalid status jumps.
- `log_event()`: appends structured changes to **Task 1's existing** `audit_events` table, setting actor and retaining nullable `import_batch_id` for IT events.
- `ticket_history()`: appends a ticket-specific timeline event and supporting note.
- `allowed_ticket()` and `require_ticket()`: centralise read/write rules; employee reads own, technician writes assigned only, admin all.
- `sla_status()`: derives `On track`, `Overdue`, `Met`, `Breached` or `Closed` from dates/current status.
- `ticket_dict()`: serialises SQLAlchemy ticket and optional history to JSON including reference, employee, technician, asset, SLA and timestamps.

### Inventory routes and service (`app/routers/assets.py`, `app/services/asset_service.py`)

- `asset_query()`: eager-loads the current holder for display.
- `list_assets()`: Admin/Technician inventory search across tag, serial and model; also filters device type/status and pages results.
- `create_asset()`: inserts and validates a new Available device; returns HTTP 409 on duplicate tag/serial; logs creation.
- `get_asset()`: displays a single accessible record.
- `edit_asset()`: modifies model/OS/warranty/notes/device status; blocks changing assigned devices directly and invalid warranty dates.
- `assign_asset()`: validates an active Employee recipient and invokes atomic `change_assignment()`.
- `return_asset()`: invokes atomic return to Available.
- `asset_dict()`: formats dates, current assignee and metadata.
- `change_assignment()`: conditional SQL mutation + append-only movement + shared audit event, all committed by the router.

### Pages (`app/routers/pages.py`, `app/routers/dashboard.py`)

- `pages.render()`: supplies logged-in identity and CSRF to Jinja templates.
- `login_page()`: renders unauthenticated sign-in.
- `tickets_page()`, `new_ticket_page()`, `ticket_page()`: return role-filtered ticket lists, owned-device picker and detailed timeline/technician controls.
- `assets_page()`: creates the inventory page for IT roles and supplies eligible employees for assignment dropdowns.
- `users_page()`: Admin-only account administration.
- `dashboard.dashboard()`: delivers Task 2 open/resolved/high/overdue/device counts and recent technician audit events; **preserves Task 1 claims charts/uploads only for Admin**. Unauthenticated users are shown the login form.

### Reports (`app/routers/it_reports.py`, `app/services/it_report_service.py`)

- `stream()`: returns a real XLSX download with appropriate Excel MIME type and filename.
- `export_tickets()`, `export_assets()`, `export_workload()`: enforce server-side IT/Admin reporting permissions.
- `tickets_report()`: pulls tickets with resolution details, asset tags and SLA outcomes; adds COUNTIF summary formulas.
- `inventory_report()`: exports device metadata, assignment/warranty and COUNTIF summary formulas.
- `workload_report()`: groups technician ticket counts and work states for planning.
- `finish()`: consistently applies Task 1 header styling, freeze panes, filters, widths, workbook recalc flag and returns an in-memory BytesIO object.

### Setup (`scripts/`)

- `migrate_task2.main()`: checks the existing Task 1 tables, parses `GO` batches from the incremental SQL Server script and runs its transactional DDL over the existing `app/db.py` engine.
- `configure_local.main()`: creates or updates `.env` with a cryptographically random signing key without overwriting existing DB variables or previously set keys.
- `seed_task2.main()`: insert-only repeatable demo setup for local fake accounts, six devices and four example support tickets.
- `03_task2_migration.sql`: SQL Server idempotent DDL and Task 1 audit extension; execute directly in SSMS if preferred.
- `04_task2_checks.sql`: reporting and verification SQL for ticket lifecycle, asset movement, audit events, overdue tickets, duplicate tags and original claims row counts.

## Migrations and data safety

Before upgrade: back up SQL Server. The migration script uses `SET XACT_ABORT ON; BEGIN TRANSACTION; ... COMMIT TRANSACTION;`. In the same transaction it adds the five new tables and modifies only the necessary audit structure. If a statement fails, SQL Server rolls back the transaction. Existing Task 1 import events retain their import batch IDs. Running the script twice doesn't duplicate tables or indexes. **Do not use `Base.metadata.create_all()` as a replacement for an ALTER migration on an existing Task 1 database**.

For the next project milestone, add a separate `scripts/05_task3_migration.sql` and keep all existing source modules rather than duplicating the app.

## End-to-end test of the laptop incident

`tests/test_laptop_walkthrough.py::test_laptop_fault_reported_assigned_investigated_resolved_closed` creates an available fictional laptop, assigns it to an employee, authenticates as that employee to report an issue, authenticates as Admin to assign a technician, authenticates as Technician to add notes and resolve, and returns to Admin to close. It verifies the audit trail, six chronological ticket history entries, device assignment and Excel report response. This follows the browser walkthrough step by step without touching SQL Server during unit tests.
