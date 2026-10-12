# Task 5 — Architecture and exact file-level responsibilities

Task 5 **extends** the existing Task 4 release of the FastAPI application. It uses the *same* SQLAlchemy `Base`, `get_db`, `User`, `Ticket`, `TicketHistory`, `AuditEvent`, session cookies, CSRF and `ClaimsITOpsDemo` database. It makes **no live directory, phone, antivirus or firewall changes**. All tasks 1–4 endpoints and schema are unchanged except the shared audit type allowlist.

## Data flow and ownership

```text
Browser /operations (Jinja2, existing base.html + app.js)
  | HTTP session + role + CSRF
  +-- /api/operations/network/* ---- operations_service.py ----> fixed local / allowlisted checks
  |                 |                                        -> network_checks -> ticket if failure
  +-- /api/operations/health/* ----- operations_service.py ----> mock / fixed read-only PowerShell
  |                                                          -> device_health_checks -> ticket if warning
  +-- /api/operations/calls/* ------ phone_service.py ---------> call_logs (unique call_reference)
  +-- /api/operations/ivr/* -------- phone_service.py ---------> ivr_rules (+ audit event)
  +-- /api/operations/backups/* --- backup_service.py ---------> ZIP JSON snapshot + SHA256 verification
  |                                                          -> backup_jobs -> ticket if failure
  +-- /api/operations/monitoring/events ------------------------> monitoring_events

Separate authorised admin operations:
  SSMS / sqlcmd -> 11_sqlserver_full_backup.sql -> C:\NorthstarLabBackups\*.bak
  SSMS ONLY     -> 12_restore_only_to_lab.sql -> ClaimsITOpsRestoreLab (never ClaimsITOpsDemo)
```

## New files

| Relative path | Detailed responsibility |
|---|---|
| `app/operations_schemas.py` | Pydantic input limits and types; no shell command arguments or arbitrary host arrays |
| `app/services/operations_service.py` | `_authorise` allowlist, `_resolve` private-address checks, `_ip_config` fixed Windows command, `_check` TCP/DNS/IPConfig, `_open_incident` Task 2 SLA and ticket history, `run_network_check`, `read_health`, `save_health` and `MonitoringEvent` + `AuditEvent` |
| `app/services/phone_service.py` | Validate UTF-8 CSV and each row; skip already imported call references, report bad rows, upsert IVR rules, simulate route only |
| `app/services/backup_service.py` | Admin-only selected-table archive exports; manifest and SHA-256 verification, path restriction, no live restore, failure escalation |
| `app/routers/operations.py` | API routes enforcing Admin/Technician read/mutate privileges and CSRF on changes |
| `app/routers/operations_pages.py` | Consolidated Jinja2 page with latest results, stats, tickets, backups and audit |
| `app/templates/operations.html` | Forms, tables and JavaScript interactions via existing `requestJSON` helper; no direct shell |
| `scripts/09_task5_migration.sql` | Additive table/index/constraint migration and audit allowlist extension |
| `scripts/migrate_task5.py` | CLI migration runner with prerequisite verification and GO batch splitting |
| `scripts/10_task5_checks.sql` | SSMS cross-module record counts, reporting and incident joins |
| `scripts/11_sqlserver_full_backup.sql` | Explicit lab-only backup, checksum, RESTORE VERIFYONLY and backup-job logging |
| `scripts/12_restore_only_to_lab.sql` | Guarded restore to uniquely named **separate** database, relocated data/log files, refuses to overwrite |
| `scripts/seed_task5.py` | Idempotent mock IVR and call seeding plus initial simulated health/network readings |
| `scripts/generate_task5_calls.py` | Deterministic 60 fictional call records |
| `scripts/inspect_recovery_export.py` | Offline read-only ZIP manifest integrity and row-count verification |
| `powershell/Get-NorthstarWindowsHealth.ps1` | Standalone fixed read-only Defender + CIM commands |
| `powershell/Invoke-NorthstarSqlBackup.ps1` | Default dry-run, `-Execute` explicitly required, local SQL Express only |
| `tests/test_task5_operations.py` | Security, validation, idempotency, incident reuse, reporting, recovery tamper evidence and cross-task regression |
| `sample_data/task5_call_logs.csv` | 60 fictional local mock call log entries, no real phone data |
| `docs/NETWORK_LAB.md` | Troubleshooting playbook for TCP/IP, VLAN, switchport, gateway, DNS, VPN, firewall |
| `docs/PHONE_LAB.md` | Optional isolated Asterisk/FreePBX lab without trunks/external network |
| `docs/INTERVIEW_DEMO.md` | 8-minute cross-task interview demonstration script |

## Modified files

| Relative path | Change |
|---|---|
| `app/models.py` | Six new declarative classes; `AuditEvent.event_type` includes Task 5 types; Task 1–4 classes unchanged |
| `app/main.py` | Registers two new routers; retains all existing routers |
| `app/templates/base.html` | Adds Operations navigation for Admin/Technician |
| `.env.example` | Local allowlists, mock health and export location without secrets |
| `.gitignore` | Excludes secrets, credential files, local logs, `.bak` and private recovery exports |
| `README.md` | Fresh Windows setup, all five tasks, migration, verification and restore instructions |

## Database schema and constraints

* `network_checks`: `check_type` IPConfig/DNS/TCP, `result` Pass/Fail/Unavailable, elapsed nonnegative, actor FK and optional linked ticket FK; index timestamp.
* `device_health_checks`: local device, OS, Defender result, age, disk usage, status, details and optional ticket; fields are nullable when status unavailable.
* `call_logs`: unique reference, direction and outcome enums, nonnegative 24-hour duration, date/route/extension.
* `ivr_rules`: `(menu_name,digit)` unique; allowed one-digit choice, destination kind, modifier and update timestamp.
* `backup_jobs`: export, full SQL backup or simulation; success/failure, verification hash/time, file location and optional ticket.
* `monitoring_events`: timestamp, severity, source reference, description, optional actor and linked incident.
* All six new tables use foreign keys as appropriate; original Task 1–4 primary and foreign keys are unchanged.

## Security model

Admin may run local diagnostics, view monitoring, import fictional calls, edit IVR, export and verify backups, and simulate failures. Technician may run diagnostics, capture device health, view calls and IVR and backup metadata, and simulate IVR routing, but cannot access/download exports. Employee is denied the Operations module. All POST/PUT requests use existing `X-CSRF-Token`. Incident tickets use Task 2 ticket state machine and SLA, audit records use shared Task 1 log. Cookie authentication remains bound to existing Task 2 accounts.

**No arbitrary network access:** single-target DNS/TCP only; DNS and host:port must exactly match administrator-maintained env allowlists; nonlocal requires `OPS_LAB_TARGETS_ENABLED=YES` and addresses must resolve to private non-link-local IPs. Never accept an IP range, CIDR, arbitrary port list, SSH command, shell string or URL from the API. The `OPS_HEALTH_MODE=windows` switch merely enables read-only local Defender/CIM reports. IVR has no PBX adapter.

**Recovery:** app ZIP exports are verified with SHA-256, per-table checksums, ZIP CRC and record counts. They contain unencrypted sample or application data and should be protected with NTFS access controls and an encrypted volume in any non-demo system. No API exists for restoring snapshots to the live database. SQL `.bak` uses `BACKUP ... WITH CHECKSUM` and `RESTORE VERIFYONLY`; a full isolated restore is mandatory for confidence in recoverability. Backups must be scheduled with approved Windows service rights and managed retention.
