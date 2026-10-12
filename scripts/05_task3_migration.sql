/* Task 3 additive migration for existing Task 1 + Task 2 ClaimsITOpsDemo.
   BACK UP DATABASE FIRST. Safe to re-run. Never drops employee/claim/ticket data. */
USE ClaimsITOpsDemo;
GO
SET XACT_ABORT ON;
BEGIN TRY
 BEGIN TRANSACTION;
 IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='users' AND schema_id=SCHEMA_ID('dbo'))
  THROW 51001, 'Task 2 schema missing. Apply 03_task2_migration.sql first.', 1;
 IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='claims' AND schema_id=SCHEMA_ID('dbo'))
  THROW 51002, 'Task 1 schema missing.', 1;

 /* Transition Reserved is new, and prevents Task 2 assignment of reserved laptops. */
 IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name='ck_assets_status' AND parent_object_id=OBJECT_ID('dbo.assets'))
  ALTER TABLE dbo.assets DROP CONSTRAINT ck_assets_status;
 ALTER TABLE dbo.assets WITH CHECK ADD CONSTRAINT ck_assets_status
  CHECK (status IN ('Available','Assigned','Reserved','Maintenance','Retired'));

 IF OBJECT_ID('dbo.employees','U') IS NULL
 BEGIN
  CREATE TABLE dbo.employees (
   id INT IDENTITY(1,1) PRIMARY KEY, full_name NVARCHAR(120) NOT NULL,
   department VARCHAR(30) NOT NULL, job_title NVARCHAR(120) NOT NULL,
   manager_name NVARCHAR(120) NOT NULL, start_date DATE NOT NULL,
   work_email VARCHAR(180) NOT NULL, ad_username VARCHAR(20) NOT NULL,
   status VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL,
   CONSTRAINT uq_employees_work_email UNIQUE(work_email),
   CONSTRAINT uq_employees_ad_username UNIQUE(ad_username),
   CONSTRAINT ck_employees_department CHECK (department IN ('Claims','Operations','Finance','HR','IT')),
   CONSTRAINT ck_employees_status CHECK (status IN ('Prepared','Active','Offboarding','Offboarded'))
  );
 END;
 IF OBJECT_ID('dbo.onboarding_requests','U') IS NULL
 BEGIN
  CREATE TABLE dbo.onboarding_requests (
   id INT IDENTITY(1,1) PRIMARY KEY, employee_id INT NOT NULL,
   requested_by INT NOT NULL, requested_groups_json NVARCHAR(MAX) NOT NULL,
   device_requirements_json NVARCHAR(MAX) NOT NULL, status VARCHAR(20) NOT NULL,
   created_at DATETIME NOT NULL, activated_at DATETIME NULL,
   CONSTRAINT uq_onboarding_employee UNIQUE(employee_id),
   CONSTRAINT fk_onboarding_employee FOREIGN KEY(employee_id) REFERENCES dbo.employees(id),
   CONSTRAINT fk_onboarding_actor FOREIGN KEY(requested_by) REFERENCES dbo.users(id),
   CONSTRAINT ck_onboarding_status CHECK(status IN ('Prepared','Attention','Activated'))
  );
 END;
 IF OBJECT_ID('dbo.offboarding_requests','U') IS NULL
 BEGIN
  CREATE TABLE dbo.offboarding_requests (
   id INT IDENTITY(1,1) PRIMARY KEY, employee_id INT NOT NULL,
   requested_by INT NOT NULL, approved_by INT NULL,
   last_working_date DATE NOT NULL, reason NVARCHAR(500) NOT NULL,
   status VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL,
   approved_at DATETIME NULL, completed_at DATETIME NULL,
   CONSTRAINT fk_offboarding_employee FOREIGN KEY(employee_id) REFERENCES dbo.employees(id),
   CONSTRAINT fk_offboarding_requester FOREIGN KEY(requested_by) REFERENCES dbo.users(id),
   CONSTRAINT fk_offboarding_approver FOREIGN KEY(approved_by) REFERENCES dbo.users(id),
   CONSTRAINT ck_offboarding_status CHECK(status IN ('PendingApproval','Approved','Completed','Attention'))
  );
 END;
 IF OBJECT_ID('dbo.provisioning_actions','U') IS NULL
 BEGIN
  CREATE TABLE dbo.provisioning_actions (
   id INT IDENTITY(1,1) PRIMARY KEY, employee_id INT NOT NULL,
   onboarding_request_id INT NULL, offboarding_request_id INT NULL,
   action_type VARCHAR(40) NOT NULL, target NVARCHAR(200) NOT NULL,
   status VARCHAR(20) NOT NULL, result_detail NVARCHAR(1000) NOT NULL,
   created_at DATETIME NOT NULL,
   CONSTRAINT fk_provisioning_employee FOREIGN KEY(employee_id) REFERENCES dbo.employees(id),
   CONSTRAINT fk_provisioning_onboard FOREIGN KEY(onboarding_request_id) REFERENCES dbo.onboarding_requests(id),
   CONSTRAINT fk_provisioning_offboard FOREIGN KEY(offboarding_request_id) REFERENCES dbo.offboarding_requests(id),
   CONSTRAINT ck_provisioning_status CHECK(status IN ('Prepared','Mocked','Failed','ManualRequired')),
   CONSTRAINT ck_provisioning_one_request CHECK(
    (onboarding_request_id IS NOT NULL AND offboarding_request_id IS NULL) OR
    (onboarding_request_id IS NULL AND offboarding_request_id IS NOT NULL))
  );
 END;
 IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_provisioning_employee' AND object_id=OBJECT_ID('dbo.provisioning_actions'))
  CREATE INDEX ix_provisioning_employee ON dbo.provisioning_actions(employee_id);
 IF OBJECT_ID('dbo.approval_records','U') IS NULL
 BEGIN
  CREATE TABLE dbo.approval_records (
   id INT IDENTITY(1,1) PRIMARY KEY, offboarding_request_id INT NOT NULL,
   approver_user_id INT NOT NULL, decision VARCHAR(20) NOT NULL,
   comment NVARCHAR(500) NOT NULL, decided_at DATETIME NOT NULL,
   CONSTRAINT uq_approval_offboarding UNIQUE(offboarding_request_id),
   CONSTRAINT fk_approval_offboard FOREIGN KEY(offboarding_request_id) REFERENCES dbo.offboarding_requests(id),
   CONSTRAINT fk_approval_actor FOREIGN KEY(approver_user_id) REFERENCES dbo.users(id),
   CONSTRAINT ck_approval_decision CHECK(decision IN ('Approved','Rejected'))
  );
 END;
 IF OBJECT_ID('dbo.asset_reservations','U') IS NULL
 BEGIN
  CREATE TABLE dbo.asset_reservations (
   id INT IDENTITY(1,1) PRIMARY KEY, asset_id INT NOT NULL,
   employee_id INT NOT NULL, onboarding_request_id INT NOT NULL,
   status VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL,
   released_at DATETIME NULL,
   CONSTRAINT fk_reservation_asset FOREIGN KEY(asset_id) REFERENCES dbo.assets(id),
   CONSTRAINT fk_reservation_employee FOREIGN KEY(employee_id) REFERENCES dbo.employees(id),
   CONSTRAINT fk_reservation_onboard FOREIGN KEY(onboarding_request_id) REFERENCES dbo.onboarding_requests(id),
   CONSTRAINT ck_reservation_status CHECK(status IN ('Reserved','Released'))
  );
 END;
 IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='uq_asset_active_reservation' AND object_id=OBJECT_ID('dbo.asset_reservations'))
  CREATE UNIQUE INDEX uq_asset_active_reservation ON dbo.asset_reservations(asset_id) WHERE status='Reserved';
 IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='uq_onboarding_active_reservation' AND object_id=OBJECT_ID('dbo.asset_reservations'))
  CREATE UNIQUE INDEX uq_onboarding_active_reservation ON dbo.asset_reservations(onboarding_request_id) WHERE status='Reserved';

 /* Extend the ORIGINAL audit_events constraint; retain all Task 1/2 entries. */
 IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name='ck_audit_events_type' AND parent_object_id=OBJECT_ID('dbo.audit_events'))
  ALTER TABLE dbo.audit_events DROP CONSTRAINT ck_audit_events_type;
 ALTER TABLE dbo.audit_events WITH CHECK ADD CONSTRAINT ck_audit_events_type CHECK (event_type IN (
  'IMPORT_COMPLETED','TICKET_CREATED','TICKET_UPDATED','TICKET_ASSIGNED','TICKET_NOTE',
  'ASSET_CREATED','ASSET_UPDATED','ASSET_ASSIGNED','ASSET_RETURNED','USER_CREATED','USER_UPDATED',
  'EMPLOYEE_CREATED','EMPLOYEE_ACTIVATED','ONBOARDING_PREPARED','OFFBOARDING_REQUESTED',
  'OFFBOARDING_APPROVED','OFFBOARDING_COMPLETED','ASSET_RESERVED','ASSET_RESERVATION_RELEASED'));
 COMMIT TRANSACTION;
END TRY
BEGIN CATCH
 IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
 THROW;
END CATCH;
GO
PRINT 'Task 3 additive migration completed; Task 1/2 data retained.';
GO
