# Northstar Claims — 8-minute IT Support portfolio interview demonstration

Prepare in advance: start SQL Server Express and FastAPI, sign in to localhost as demo Admin. Keep SSMS, `/`, `/tickets`, `/assets`, `/employees`, `/claims-management`, `/workflow-logs`, and `/operations` open in browser tabs. All data and external integration responses are fictional.

| Time | Live action | Technical explanation |
|---|---|---|
| 0:00–1:20 | Task 1: upload fictional claims Excel or show an imported batch. Open claims SQL and Excel report. | 1,000 rows → 900 valid and 100 rejected, validation, idempotent SHA-256 import and unique SQL claim IDs. |
| 1:20–2:40 | Task 2: open laptop fault ticket, assign technician, show SLA and linked device in Inventory. | Roles, CSRF, ticket transitions, history, warranty, conflict-safe assignment. |
| 2:40–3:50 | Task 3: prepare Alex Morgan (Claims) onboarding, reserve a laptop, show AD and Google mock checklist. | Security group mapping, dry-run AD, mock Google Workspace, two-person admin offboarding approval. |
| 3:50–5:00 | Task 4: open claim `NCL-009999`, show Evidence Required → Ready for Review → Resolved and execution history. | Mock Zoho CRM V8, idempotent workflow events, failure log and Task 2 escalation. |
| 5:00–6:20 | Task 5: `/operations`, DNS localhost, TCP localhost:8000, capture mock Windows health. | Strict approved host:port allowlist, latency, Defender/disk reporting, support incident for failed check. |
| 6:20–7:05 | Task 5: import/view 60 fictional calls, edit Main menu digit 1, simulate routing to ClaimsQueue. | IVR rules saved in SQL, tracked edits; no carrier, trunks or external calls. |
| 7:05–8:30 | Task 5: export selected claims/tickets/assets, verify archive and simulate backup failure to open incident. In SSMS show backup-job log. | SHA-256 + manifest, full SQL backup CHECKSUM + VERIFYONLY, separate restore target `ClaimsITOpsRestoreLab`; existing DB never overwritten. |

Closing statement: "I built one modular FastAPI/SQL Server platform to demonstrate practical end-user support, data validation, access workflows, CRM automation and infrastructure monitoring. I use role-based access, audit logging, safe mock integrations, controlled network scopes and recovery verification, with automated cross-module regression tests."

If time is limited, pre-load imports and show their reports. Do not claim SQLite tests validate SQL Server restore: demonstrate a separate SSMS restore in an isolated lab, or explicitly note that it is an environment-specific validation step.
