# Fresh Windows 11: complete Northstar Claims Tasks 1–5 setup

This complete application is for a **fictional UK claims company** and an isolated local environment. Default integrations: Active Directory dry-run; Google Workspace mock; Zoho CRM mock; phone/IVR mock; Windows health mock; local-only network diagnostics. Live account changes and external PBX calls are never made from FastAPI. The original `ClaimsITOpsDemo` database and Task 1–4 functionality are retained.

## 1. Install required software

Install **Python 3.12 x64**, **VS Code + Python extension**, **SQL Server Express (SQLEXPRESS named instance)**, **SSMS**, and **Microsoft ODBC Driver 18 for SQL Server x64**. Install optional `sqlcmd` for automated backups. Choose Windows Authentication in SQL Server setup and keep SQL Server limited to localhost/lab. Installers: https://www.python.org/downloads/windows/ ; https://code.visualstudio.com/ ; https://www.microsoft.com/en-us/sql-server/sql-server-downloads ; https://learn.microsoft.com/en-us/ssms/install/install ; https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server ; https://learn.microsoft.com/en-us/sql/tools/sqlcmd/sqlcmd-utility .

Use SSMS connection `localhost\SQLEXPRESS`, Windows Authentication. ODBC 18 may require **Trust server certificate** for the **trusted local self-signed** certificate; never generalise this production setting.

## 2. Open the actual application in VS Code

Extract the Task 5 ZIP and open `it-operations-platform/` in VS Code. In VS Code **Terminal → New Terminal** (PowerShell), run:

```powershell
py -3.12 --version
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env       # only when creating a NEW installation
python -m scripts.configure_local
python -c "import pyodbc; print(pyodbc.drivers())"
```

Make sure ODBC Driver 18 appears in the driver output. The `.env` is gitignored and holds the connection string and randomly generated signed-session secret. Preserve your **existing** `.env` when upgrading. The default example includes:

```dotenv
DB_SERVER=localhost\SQLEXPRESS
DB_NAME=ClaimsITOpsDemo
DB_ODBC_DRIVER=ODBC Driver 18 for SQL Server
ZOHO_MODE=mock
ZOHO_REAL_ENABLED=NO
GOOGLE_LAB_ENABLED=NO
OPS_DNS_TARGETS=localhost
OPS_TCP_TARGETS=localhost:8000
OPS_LAB_TARGETS_ENABLED=NO
OPS_HEALTH_MODE=mock
```

No real customer data, production tokens, secrets, SIP recordings or backup archives should be committed. `APP_COOKIE_SECURE=false` is **localhost HTTP-only**; HTTPS installations must use secure cookies, TLS certificate verification, and production-grade account policies.

## 3. Create or migrate SQL Server — choose ONE path

**Brand-new PC, no previous `ClaimsITOpsDemo`:** in SSMS run `scripts/01_create_database.sql` (F5), then in VS Code PowerShell run `python -m scripts.init_schema`. This creates *all current* SQLAlchemy tables and constraints in the new empty database in one operation. **Do not run old incremental migrations after `init_schema` on a fresh database**: they are for previously existing older installations.

**Existing Task 4 database:** first back up the working `ClaimsITOpsDemo` database in SSMS. In SSMS open `scripts/09_task5_migration.sql` and press F5, **or** run `python -m scripts.migrate_task5` in VS Code, never in parallel. This adds exactly six tables (`network_checks`, `device_health_checks`, `call_logs`, `ivr_rules`, `backup_jobs`, `monitoring_events`) and extends the audit type constraint without overwriting Tasks 1–4. Users upgrading from earlier than Task 4 must apply each earlier migration first in order.

Run `scripts/10_task5_checks.sql` in SSMS to confirm all original and new tables, incident joins and audit events. An `Invalid object name` error indicates the required migration has not been applied to the connection's database.

## 4. Seed fictional data and run the website

```powershell
python -m scripts.generate_sample_data
python -m scripts.generate_task5_calls
python -m scripts.seed_task2
python -m scripts.seed_task3
python -m scripts.seed_task4
python -m scripts.seed_task5
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Visit http://127.0.0.1:8000/login and sign in with `admin` / `NorthstarAdmin!2026` (fictional local demonstration password, never use in production). Alternative seeded roles: `tech.owen` / `NorthstarTech!2026`, `employee.ellie` / `NorthstarStaff!2026`, reviewer `admin.reviewer` / `NorthstarReview!2026`.

Pages: Task 1 main dashboard `/`; Task 2 `/tickets`, `/assets`; Task 3 `/employees`; Task 4 `/claims-management`, `/workflow-logs`, `/communication-templates`; Task 5 **`/operations`**; interactive REST API `/docs`; health `/health`.

The Task 5 seed inserts 60 fictional calls, four IVR rules, and one sample read-only network/health event if there are none. Re-running won't duplicate calls or IVR routes.

## 5. Task 5 demonstrations on /operations

**Network checks:** Run `IPConfig` with `localhost` to show Windows NIC/DNS/default-gateway data. Run `DNS` with `localhost` and `TCP` with `localhost:8000` to measure elapsed time. The configured DNS name or TCP host:port must match the `.env` allowlist exactly. Nonlocal hosts additionally require an explicitly authorised private lab and `OPS_LAB_TARGETS_ENABLED=YES`; public IPs and subnets are denied, and the API has no scan option. A failed approved check records a MonitoringEvent and creates or reuses a Task 2 incident. Standalone PowerShell commands: `Get-NetIPConfiguration`, `Resolve-DnsName localhost`, `Test-NetConnection localhost -Port 8000`, `Get-NetFirewallProfile`; do not disable any firewall. Manual VLAN/DNS/VPN/switch guide: `docs/NETWORK_LAB.md`.

**Device/antivirus health:** In default mock mode, click **Capture health**. It reports fictional Windows 11 Defender, signature age and actual filesystem disk usage. Set `OPS_HEALTH_MODE=windows` only on a Windows machine to use fixed, read-only PowerShell `Get-MpComputerStatus` and `Get-CimInstance` calls. You can run `.\powershell\Get-NorthstarWindowsHealth.ps1` directly on Windows. Defender missing/unavailable is displayed explicitly; no security controls are changed.

**Calls and IVR:** Upload `sample_data/task5_call_logs.csv` (if seeded already, all 60 are duplicates). View volume and missed-call counts. Edit the `Main` / `1` IVR menu to `Queue` / `ClaimsQueue`, simulate menu digit 1 and confirm `real_call_placed=false`. Rule changes write AuditEvent entries. See `docs/PHONE_LAB.md` for a separate host-only FreePBX/Asterisk VM lab with no SIP trunk or live accounts.

**Backups:** Admin → **Export claims, tickets and assets** generates a ZIP JSON snapshot with a SHA-256 and per-table checksums inside private `backups/`. Click **Verify**, **Download**, then use the offline, read-only verifier:

```powershell
python -m scripts.inspect_recovery_export .\backups\<actual-filename>.zip
```

Replace `<actual-filename>` with your real exported filename shown on the page. Integrity verification and ZIP CRC do **not** constitute a SQL Server restore test. Never store raw JSON exports in public repos. A deliberately corrupted/missing export flags failure and raises an incident. **Simulate failed backup** records a harmless failure and creates a linked helpdesk ticket without touching SQL files.

## 6. SQL Server backup and recovery — SSMS / approved local Windows lab only

The website cannot run backup or restore SQL and has no restore API. On a **test** SQL Server host, create `C:\NorthstarLabBackups` and give the SQL Server Express **service identity** write permission. In SSMS execute `scripts/11_sqlserver_full_backup.sql`. This creates `C:\NorthstarLabBackups\ClaimsITOpsDemo_full.bak`, uses `BACKUP WITH CHECKSUM`, runs `RESTORE VERIFYONLY WITH CHECKSUM`, then logs a row in `backup_jobs`. SQL service identity, not your personal Windows user, must write the backup file. Any failure is logged if possible; an actual full restore is still essential for disaster-recovery validation.

In SSMS inspect `RESTORE FILELISTONLY FROM DISK=N'C:\NorthstarLabBackups\ClaimsITOpsDemo_full.bak';` and verify source logical names and file count. After written approval, execute `scripts/12_restore_only_to_lab.sql` first in inspection mode; review its `RESTORE FILELISTONLY` output, then **change `@LabRestoreConfirmed` from 0 to 1 in the SQL file for the approved isolated lab and rerun** on the same **isolated** server. It refuses an existing restore target and hardcodes the new database **`ClaimsITOpsRestoreLab`** with distinct MDF/LDF paths; **it cannot accept or replace `ClaimsITOpsDemo`**. Compare `SELECT COUNT(*) FROM ClaimsITOpsRestoreLab.dbo.claims;` with the working DB. Do not run these exercises on a production server.

Windows PowerShell wrapper (preview by default):

```powershell
.\powershell\Invoke-NorthstarSqlBackup.ps1
# Explicitly authorised lab backup only, requires sqlcmd installed:
.\powershell\Invoke-NorthstarSqlBackup.ps1 -Execute
```

**Task Scheduler:** Windows Task Scheduler → Create Task → `Northstar SQL Lab Backup` → set an approved **local service identity**, a daily time when the lab server is on, and action **Start a program** `powershell.exe` with arguments `-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "C:\YOUR\ABSOLUTE\PROJECT\powershell\Invoke-NorthstarSqlBackup.ps1" -Execute`. Set Start in to the project directory. Make sure the service identity can use Windows Integrated Authentication and write the SQL backup directory. Test the task once, check Last Run Result and query `dbo.backup_jobs`. In this demo the `.bak` filename is fixed and each run overwrites the previous backup file: **configure separate retention, offline encrypted copies and recovery-point objectives for any serious backup strategy**. Never schedule the restore script.

Sources: https://learn.microsoft.com/en-us/sql/t-sql/statements/restore-statements-verifyonly-transact-sql ; https://learn.microsoft.com/en-us/sql/t-sql/statements/restore-statements-arguments-transact-sql .

## 7. Tests, error handling and interview demo

In VS Code PowerShell:

```powershell
python -m pytest -q
python -m pytest tests/test_task5_operations.py -v
python -m compileall -q app scripts
```

The combined tests use isolated SQLite with mock services. They validate preserved claims, ticketing and roles, onboarding, workflow transitions, network allowlists, device-health warnings, call imports, IVR updates, backup corruption and incidents. **SQL Server/ODBC connection, Windows PowerShell, Task Scheduler and guarded test restore require validation on your actual Windows lab**.

Common issues: `401` means not signed in; `403` means role, CSRF or target not allowed; `422` indicates invalid CSV/schema; `Invalid object name network_checks` means run migration; ODBC errors require driver and SQL service check; Defender status unavailable may be normal with non-Defender antivirus; missing `sqlcmd` means use SSMS; backup access denied means SQL Server service identity cannot write local folder; restore refuses an existing lab DB as intended. For failures, check `/operations`, `/tickets`, SSMS `scripts/10_task5_checks.sql` and Task Scheduler history.

**Architecture:** `docs/TASK5_ARCHITECTURE.md` details every new and modified file and SQL table, while existing Task 1–4 architecture is preserved. **Networking lab:** `docs/NETWORK_LAB.md`. **IVR lab:** `docs/PHONE_LAB.md`. **Interview script:** `docs/INTERVIEW_DEMO.md` (~8 minutes across all five modules).
