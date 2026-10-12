/* TASK 4 — incremental, re-runnable SQL Server migration. BACK UP FIRST.
   Does not drop claims, users, helpdesk tickets, assets, or Task 3 records. */
USE ClaimsITOpsDemo;
GO
SET XACT_ABORT ON;
BEGIN TRY
 BEGIN TRANSACTION;
 IF OBJECT_ID('dbo.claims','U') IS NULL OR OBJECT_ID('dbo.tickets','U') IS NULL
  THROW 51041, 'Tasks 1–3 must be installed first.', 1;

 IF OBJECT_ID('dbo.claim_crm_states','U') IS NULL
 BEGIN
  CREATE TABLE dbo.claim_crm_states (
   id INT IDENTITY(1,1) PRIMARY KEY,
   claim_id INT NOT NULL, zoho_record_id VARCHAR(80) NULL,
   stage VARCHAR(30) NOT NULL, assigned_handler NVARCHAR(120) NULL,
   missing_documents BIT NOT NULL CONSTRAINT df_crm_missing DEFAULT(0),
   integration_status VARCHAR(20) NOT NULL, last_updated DATETIME NOT NULL,
   synced_at DATETIME NULL, completed_at DATETIME NULL,
   CONSTRAINT fk_crm_claim FOREIGN KEY(claim_id) REFERENCES dbo.claims(id),
   CONSTRAINT uq_claim_crm_claim UNIQUE(claim_id),
   CONSTRAINT ck_crm_stage CHECK(stage IN ('New','Assigned','Evidence Required','Ready for Review','Resolved')),
   CONSTRAINT ck_crm_integration CHECK(integration_status IN ('Not Synced','Synced','Failed'))
  );
 END;
 IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='uq_claim_crm_zoho' AND object_id=OBJECT_ID('dbo.claim_crm_states'))
  CREATE UNIQUE INDEX uq_claim_crm_zoho ON dbo.claim_crm_states(zoho_record_id) WHERE zoho_record_id IS NOT NULL;
 IF OBJECT_ID('dbo.workflow_rules','U') IS NULL
 BEGIN
  CREATE TABLE dbo.workflow_rules (
   id INT IDENTITY(1,1) PRIMARY KEY, name NVARCHAR(120) NOT NULL,
   event_type VARCHAR(30) NOT NULL, action_type VARCHAR(30) NOT NULL,
   parameters_json NVARCHAR(MAX) NOT NULL, enabled BIT NOT NULL, created_at DATETIME NOT NULL,
   CONSTRAINT uq_workflow_rule_name UNIQUE(name),
   CONSTRAINT ck_workflow_rule_event CHECK(event_type IN ('submitted','missing_documents','evidence_received','resolved')),
   CONSTRAINT ck_workflow_rule_action CHECK(action_type IN ('assign_team','evidence_required','ready_for_review','resolve','demo_fail'))
  );
 END;
 IF OBJECT_ID('dbo.workflow_executions','U') IS NULL
 BEGIN
  CREATE TABLE dbo.workflow_executions (
   id INT IDENTITY(1,1) PRIMARY KEY, claim_id INT NOT NULL, rule_id INT NOT NULL,
   event_key VARCHAR(100) NOT NULL, status VARCHAR(15) NOT NULL,
   input_status VARCHAR(30) NOT NULL, output_status VARCHAR(30) NULL,
   error_reason NVARCHAR(1000) NULL, retry_count INT NOT NULL,
   support_ticket_id INT NULL, started_at DATETIME NOT NULL, finished_at DATETIME NULL,
   CONSTRAINT fk_exec_claim FOREIGN KEY(claim_id) REFERENCES dbo.claims(id),
   CONSTRAINT fk_exec_rule FOREIGN KEY(rule_id) REFERENCES dbo.workflow_rules(id),
   CONSTRAINT fk_exec_ticket FOREIGN KEY(support_ticket_id) REFERENCES dbo.tickets(id),
   CONSTRAINT uq_workflow_exact_event UNIQUE(claim_id,rule_id,event_key),
   CONSTRAINT ck_workflow_execution_status CHECK(status IN ('Success','Failed')),
   CONSTRAINT ck_workflow_retry_count CHECK(retry_count BETWEEN 0 AND 3)
  );
 END;
 IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_workflow_status' AND object_id=OBJECT_ID('dbo.workflow_executions'))
  CREATE INDEX ix_workflow_status ON dbo.workflow_executions(status,started_at);

 IF OBJECT_ID('dbo.workflow_transitions','U') IS NULL
 BEGIN
  CREATE TABLE dbo.workflow_transitions (
   id INT IDENTITY(1,1) PRIMARY KEY, execution_id INT NOT NULL, claim_id INT NOT NULL,
   from_stage VARCHAR(30) NOT NULL, to_stage VARCHAR(30) NOT NULL, occurred_at DATETIME NOT NULL,
   CONSTRAINT fk_transition_exec FOREIGN KEY(execution_id) REFERENCES dbo.workflow_executions(id),
   CONSTRAINT fk_transition_claim FOREIGN KEY(claim_id) REFERENCES dbo.claims(id),
   CONSTRAINT uq_transition_execution UNIQUE(execution_id)
  );
 END;
 IF OBJECT_ID('dbo.crm_operations','U') IS NULL
 BEGIN
  CREATE TABLE dbo.crm_operations (
   id INT IDENTITY(1,1) PRIMARY KEY, operation_key VARCHAR(100) NOT NULL,
   claim_id INT NOT NULL, operation VARCHAR(30) NOT NULL, payload_json NVARCHAR(MAX) NOT NULL,
   status VARCHAR(15) NOT NULL, retry_count INT NOT NULL,
   error_reason NVARCHAR(1000) NULL, created_at DATETIME NOT NULL, finished_at DATETIME NULL,
   CONSTRAINT fk_crmop_claim FOREIGN KEY(claim_id) REFERENCES dbo.claims(id),
   CONSTRAINT uq_crm_operation_key UNIQUE(operation_key),
   CONSTRAINT ck_crm_operation_status CHECK(status IN ('Success','Failed')),
   CONSTRAINT ck_crm_operation_retry CHECK(retry_count BETWEEN 0 AND 3)
  );
 END;
 IF OBJECT_ID('dbo.communication_templates','U') IS NULL
 BEGIN
  CREATE TABLE dbo.communication_templates (
   id INT IDENTITY(1,1) PRIMARY KEY, kind VARCHAR(30) NOT NULL,
   subject NVARCHAR(200) NOT NULL, body NVARCHAR(4000) NOT NULL,
   updated_at DATETIME NOT NULL, updated_by INT NULL,
   CONSTRAINT uq_communication_kind UNIQUE(kind),
   CONSTRAINT fk_template_updater FOREIGN KEY(updated_by) REFERENCES dbo.users(id)
  );
 END;

 IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name='ck_audit_events_type' AND parent_object_id=OBJECT_ID('dbo.audit_events'))
  ALTER TABLE dbo.audit_events DROP CONSTRAINT ck_audit_events_type;
 ALTER TABLE dbo.audit_events WITH CHECK ADD CONSTRAINT ck_audit_events_type CHECK(event_type IN (
 'IMPORT_COMPLETED','TICKET_CREATED','TICKET_UPDATED','TICKET_ASSIGNED','TICKET_NOTE',
 'ASSET_CREATED','ASSET_UPDATED','ASSET_ASSIGNED','ASSET_RETURNED','USER_CREATED','USER_UPDATED',
 'EMPLOYEE_CREATED','EMPLOYEE_ACTIVATED','ONBOARDING_PREPARED','OFFBOARDING_REQUESTED',
 'OFFBOARDING_APPROVED','OFFBOARDING_COMPLETED','ASSET_RESERVED','ASSET_RESERVATION_RELEASED',
 'CLAIM_WORKFLOW','CLAIM_CRM_SYNC','CLAIM_TEMPLATE_UPDATED','CLAIM_WORKFLOW_FAILED'));
 COMMIT TRANSACTION;
END TRY
BEGIN CATCH
 IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
 THROW;
END CATCH;
GO
PRINT 'Task 4 migration complete; claims and prior task tables retained.';
GO
