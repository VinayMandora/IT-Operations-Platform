/* Task 5: ADDITIVE SQL Server migration. Full backup and Tasks 1-4 required.
   Safe to rerun: creates only missing Task 5 tables and replaces the audit allowlist. */
USE ClaimsITOpsDemo;
GO
SET XACT_ABORT ON;
BEGIN TRY
 BEGIN TRANSACTION;
 IF OBJECT_ID('dbo.claim_crm_states','U') IS NULL OR OBJECT_ID('dbo.tickets','U') IS NULL
   THROW 51050, 'Apply Tasks 1-4 migrations before Task 5.', 1;
 IF OBJECT_ID('dbo.network_checks','U') IS NULL
 BEGIN
  CREATE TABLE dbo.network_checks (
   id INT IDENTITY(1,1) PRIMARY KEY, check_type VARCHAR(20) NOT NULL,
   target VARCHAR(160) NOT NULL, port INT NULL, result VARCHAR(20) NOT NULL,
   elapsed_ms NUMERIC(12,2) NULL, details_json NVARCHAR(MAX) NOT NULL,
   ticket_id INT NULL, actor_user_id INT NOT NULL, created_at DATETIME NOT NULL,
   CONSTRAINT ck_network_type CHECK(check_type IN ('IPConfig','DNS','TCP')),
   CONSTRAINT ck_network_result CHECK(result IN ('Pass','Fail','Unavailable')),
   CONSTRAINT ck_network_elapsed CHECK(elapsed_ms IS NULL OR elapsed_ms >= 0),
   CONSTRAINT fk_network_ticket FOREIGN KEY(ticket_id) REFERENCES dbo.tickets(id),
   CONSTRAINT fk_network_actor FOREIGN KEY(actor_user_id) REFERENCES dbo.users(id)
  );
 END;
 IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.network_checks') AND name='ix_network_created')
  CREATE INDEX ix_network_created ON dbo.network_checks(created_at);
 IF OBJECT_ID('dbo.device_health_checks','U') IS NULL
 BEGIN
  CREATE TABLE dbo.device_health_checks (
   id INT IDENTITY(1,1) PRIMARY KEY, hostname NVARCHAR(120) NOT NULL,
   os_description NVARCHAR(200) NOT NULL, antivirus_status VARCHAR(40) NOT NULL,
   realtime_protection VARCHAR(40) NOT NULL, definitions_age_days INT NULL,
   disk_total_bytes NUMERIC(20,0) NULL, disk_free_bytes NUMERIC(20,0) NULL,
   status VARCHAR(20) NOT NULL, details_json NVARCHAR(MAX) NOT NULL,
   ticket_id INT NULL, actor_user_id INT NOT NULL, created_at DATETIME NOT NULL,
   CONSTRAINT ck_health_status CHECK(status IN ('Healthy','Warning','Unavailable')),
   CONSTRAINT ck_health_age CHECK(definitions_age_days IS NULL OR definitions_age_days >= 0),
   CONSTRAINT ck_health_disk_total CHECK(disk_total_bytes IS NULL OR disk_total_bytes >= 0),
   CONSTRAINT ck_health_disk_free CHECK(disk_free_bytes IS NULL OR disk_free_bytes >= 0),
   CONSTRAINT fk_health_ticket FOREIGN KEY(ticket_id) REFERENCES dbo.tickets(id),
   CONSTRAINT fk_health_actor FOREIGN KEY(actor_user_id) REFERENCES dbo.users(id)
  );
 END;
 IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.device_health_checks') AND name='ix_health_created')
  CREATE INDEX ix_health_created ON dbo.device_health_checks(created_at);
 IF OBJECT_ID('dbo.call_logs','U') IS NULL
 BEGIN
  CREATE TABLE dbo.call_logs (
   id INT IDENTITY(1,1) PRIMARY KEY, call_reference VARCHAR(50) NOT NULL,
   extension VARCHAR(12) NOT NULL, occurred_at DATETIME NOT NULL,
   direction VARCHAR(10) NOT NULL, duration_seconds INT NOT NULL,
   route VARCHAR(120) NOT NULL, outcome VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL,
   CONSTRAINT uq_call_reference UNIQUE(call_reference),
   CONSTRAINT ck_call_direction CHECK(direction IN ('Inbound','Outbound')),
   CONSTRAINT ck_call_outcome CHECK(outcome IN ('Answered','Missed','Voicemail')),
   CONSTRAINT ck_call_duration CHECK(duration_seconds >= 0 AND duration_seconds <= 86400)
  );
 END;
 IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.call_logs') AND name='ix_call_occurred')
  CREATE INDEX ix_call_occurred ON dbo.call_logs(occurred_at);
 IF OBJECT_ID('dbo.ivr_rules','U') IS NULL
 BEGIN
  CREATE TABLE dbo.ivr_rules (
   id INT IDENTITY(1,1) PRIMARY KEY, menu_name VARCHAR(60) NOT NULL,
   digit VARCHAR(1) NOT NULL, label NVARCHAR(120) NOT NULL,
   destination_type VARCHAR(20) NOT NULL, destination VARCHAR(80) NOT NULL,
   enabled BIT NOT NULL, updated_at DATETIME NOT NULL, updated_by INT NULL,
   CONSTRAINT uq_ivr_menu_digit UNIQUE(menu_name,digit),
   CONSTRAINT ck_ivr_destination CHECK(destination_type IN ('Extension','Queue','Voicemail')),
   CONSTRAINT ck_ivr_digit CHECK(digit IN ('0','1','2','3','4','5','6','7','8','9')),
   CONSTRAINT fk_ivr_updater FOREIGN KEY(updated_by) REFERENCES dbo.users(id)
  );
 END;
 IF OBJECT_ID('dbo.backup_jobs','U') IS NULL
 BEGIN
  CREATE TABLE dbo.backup_jobs (
   id INT IDENTITY(1,1) PRIMARY KEY, backup_type VARCHAR(30) NOT NULL,
   result VARCHAR(15) NOT NULL, location NVARCHAR(300) NOT NULL,
   file_size NUMERIC(20,0) NULL, sha256 VARCHAR(64) NULL,
   verified_at DATETIME NULL, failure_reason NVARCHAR(1000) NULL,
   ticket_id INT NULL, actor_user_id INT NULL, created_at DATETIME NOT NULL,
   CONSTRAINT ck_backup_type CHECK(backup_type IN ('ApplicationExport','SQLFull','Simulation')),
   CONSTRAINT ck_backup_result CHECK(result IN ('Success','Failed')),
   CONSTRAINT fk_backup_ticket FOREIGN KEY(ticket_id) REFERENCES dbo.tickets(id),
   CONSTRAINT fk_backup_actor FOREIGN KEY(actor_user_id) REFERENCES dbo.users(id)
  );
 END;
 IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.backup_jobs') AND name='ix_backup_created')
  CREATE INDEX ix_backup_created ON dbo.backup_jobs(created_at);
 IF OBJECT_ID('dbo.monitoring_events','U') IS NULL
 BEGIN
  CREATE TABLE dbo.monitoring_events (
   id INT IDENTITY(1,1) PRIMARY KEY, event_type VARCHAR(50) NOT NULL,
   severity VARCHAR(15) NOT NULL, source_reference VARCHAR(100) NOT NULL,
   message NVARCHAR(1000) NOT NULL, ticket_id INT NULL,
   actor_user_id INT NULL, created_at DATETIME NOT NULL,
   CONSTRAINT ck_monitoring_severity CHECK(severity IN ('Info','Warning','Critical')),
   CONSTRAINT fk_monitor_ticket FOREIGN KEY(ticket_id) REFERENCES dbo.tickets(id),
   CONSTRAINT fk_monitor_actor FOREIGN KEY(actor_user_id) REFERENCES dbo.users(id)
  );
 END;
 IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.monitoring_events') AND name='ix_monitoring_created')
  CREATE INDEX ix_monitoring_created ON dbo.monitoring_events(created_at);
 IF EXISTS(SELECT 1 FROM sys.check_constraints WHERE name='ck_audit_events_type'
           AND parent_object_id=OBJECT_ID('dbo.audit_events'))
  ALTER TABLE dbo.audit_events DROP CONSTRAINT ck_audit_events_type;
 ALTER TABLE dbo.audit_events WITH CHECK ADD CONSTRAINT ck_audit_events_type CHECK(event_type IN (
 'IMPORT_COMPLETED','TICKET_CREATED','TICKET_UPDATED','TICKET_ASSIGNED','TICKET_NOTE',
 'ASSET_CREATED','ASSET_UPDATED','ASSET_ASSIGNED','ASSET_RETURNED','USER_CREATED','USER_UPDATED',
 'EMPLOYEE_CREATED','EMPLOYEE_ACTIVATED','ONBOARDING_PREPARED','OFFBOARDING_REQUESTED',
 'OFFBOARDING_APPROVED','OFFBOARDING_COMPLETED','ASSET_RESERVED','ASSET_RESERVATION_RELEASED',
 'CLAIM_WORKFLOW','CLAIM_CRM_SYNC','CLAIM_TEMPLATE_UPDATED','CLAIM_WORKFLOW_FAILED',
 'NETWORK_CHECK','DEVICE_HEALTH','CALLS_IMPORTED','IVR_UPDATED','BACKUP_CREATED','BACKUP_VERIFIED','BACKUP_FAILED'));
 COMMIT TRANSACTION;
END TRY
BEGIN CATCH
 IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
 THROW;
END CATCH;
GO
PRINT 'Task 5 migration complete; Tasks 1-4 data retained.';
GO
