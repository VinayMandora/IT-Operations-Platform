/* Non-destructive SQL Server Task 1 -> Task 2 migration.
   Execute in SSMS (F5) or: python -m scripts.migrate_task2.
   Existing dbo.claims/import_batches/rejected_rows/audit_events data is retained.
*/
USE ClaimsITOpsDemo;
GO
SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.users', N'U') IS NULL
BEGIN
 CREATE TABLE dbo.users (
  id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  username VARCHAR(60) NOT NULL,
  full_name NVARCHAR(120) NOT NULL,
  email VARCHAR(180) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(20) NOT NULL,
  is_active BIT NOT NULL,
  created_at DATETIME NOT NULL,
  CONSTRAINT uq_users_username UNIQUE (username),
  CONSTRAINT uq_users_email UNIQUE (email),
  CONSTRAINT ck_users_role CHECK (role IN ('Admin','Technician','Employee'))
 );
END;

IF OBJECT_ID(N'dbo.assets', N'U') IS NULL
BEGIN
 CREATE TABLE dbo.assets (
  id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  asset_tag VARCHAR(40) NOT NULL,
  serial_number VARCHAR(100) NOT NULL,
  device_type VARCHAR(20) NOT NULL,
  manufacturer NVARCHAR(80) NOT NULL,
  model NVARCHAR(120) NOT NULL,
  operating_system NVARCHAR(100) NULL,
  purchase_date DATE NOT NULL,
  warranty_expiry DATE NULL,
  status VARCHAR(20) NOT NULL,
  assigned_employee_id INT NULL,
  assigned_at DATETIME NULL,
  notes NVARCHAR(1000) NOT NULL,
  created_at DATETIME NOT NULL,
  CONSTRAINT uq_assets_tag UNIQUE (asset_tag),
  CONSTRAINT uq_assets_serial UNIQUE (serial_number),
  CONSTRAINT ck_assets_type CHECK (device_type IN ('Laptop','Desktop','Printer','Router','Switch')),
  CONSTRAINT ck_assets_status CHECK (status IN ('Available','Assigned','Maintenance','Retired')),
  CONSTRAINT ck_assets_warranty CHECK (warranty_expiry IS NULL OR warranty_expiry >= purchase_date),
  CONSTRAINT ck_assets_assignment CHECK ((status = 'Assigned' AND assigned_employee_id IS NOT NULL) OR (status <> 'Assigned' AND assigned_employee_id IS NULL)),
  CONSTRAINT fk_assets_employee FOREIGN KEY (assigned_employee_id) REFERENCES dbo.users(id)
 );
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_assets_status' AND object_id = OBJECT_ID('dbo.assets'))
 CREATE INDEX ix_assets_status ON dbo.assets(status);

IF OBJECT_ID(N'dbo.tickets', N'U') IS NULL
BEGIN
 CREATE TABLE dbo.tickets (
  id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  employee_id INT NOT NULL,
  assigned_technician_id INT NULL,
  affected_asset_id INT NULL,
  title NVARCHAR(160) NOT NULL,
  description NVARCHAR(3000) NOT NULL,
  category VARCHAR(30) NOT NULL,
  priority VARCHAR(10) NOT NULL,
  status VARCHAR(20) NOT NULL,
  resolution_details NVARCHAR(3000) NULL,
  created_at DATETIME NOT NULL,
  assigned_at DATETIME NULL,
  resolved_at DATETIME NULL,
  closed_at DATETIME NULL,
  sla_due_at DATETIME NOT NULL,
  CONSTRAINT fk_tickets_employee FOREIGN KEY (employee_id) REFERENCES dbo.users(id),
  CONSTRAINT fk_tickets_technician FOREIGN KEY (assigned_technician_id) REFERENCES dbo.users(id),
  CONSTRAINT fk_tickets_asset FOREIGN KEY (affected_asset_id) REFERENCES dbo.assets(id),
  CONSTRAINT ck_tickets_category CHECK (category IN ('Hardware','Software','Network','Printer','Account Access','Other')),
  CONSTRAINT ck_tickets_priority CHECK (priority IN ('Low','Medium','High','Critical')),
  CONSTRAINT ck_tickets_status CHECK (status IN ('Open','Assigned','In Progress','Resolved','Closed'))
 );
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_tickets_status_due' AND object_id = OBJECT_ID('dbo.tickets'))
 CREATE INDEX ix_tickets_status_due ON dbo.tickets(status, sla_due_at);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_tickets_assignee' AND object_id = OBJECT_ID('dbo.tickets'))
 CREATE INDEX ix_tickets_assignee ON dbo.tickets(assigned_technician_id);

IF OBJECT_ID(N'dbo.ticket_history', N'U') IS NULL
BEGIN
 CREATE TABLE dbo.ticket_history (
  id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  ticket_id INT NOT NULL,
  actor_user_id INT NOT NULL,
  action VARCHAR(30) NOT NULL,
  previous_status VARCHAR(20) NULL,
  new_status VARCHAR(20) NULL,
  note NVARCHAR(3000) NOT NULL,
  occurred_at DATETIME NOT NULL,
  CONSTRAINT fk_history_ticket FOREIGN KEY (ticket_id) REFERENCES dbo.tickets(id),
  CONSTRAINT fk_history_actor FOREIGN KEY (actor_user_id) REFERENCES dbo.users(id)
 );
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ticket_history_ticket' AND object_id = OBJECT_ID('dbo.ticket_history'))
 CREATE INDEX ix_ticket_history_ticket ON dbo.ticket_history(ticket_id);

IF OBJECT_ID(N'dbo.asset_movements', N'U') IS NULL
BEGIN
 CREATE TABLE dbo.asset_movements (
  id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
  asset_id INT NOT NULL,
  employee_id INT NOT NULL,
  actor_user_id INT NOT NULL,
  action VARCHAR(15) NOT NULL,
  occurred_at DATETIME NOT NULL,
  CONSTRAINT fk_movement_asset FOREIGN KEY (asset_id) REFERENCES dbo.assets(id),
  CONSTRAINT fk_movement_employee FOREIGN KEY (employee_id) REFERENCES dbo.users(id),
  CONSTRAINT fk_movement_actor FOREIGN KEY (actor_user_id) REFERENCES dbo.users(id)
 );
END;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_asset_movements_asset' AND object_id = OBJECT_ID('dbo.asset_movements'))
 CREATE INDEX ix_asset_movements_asset ON dbo.asset_movements(asset_id);

/* Task 1's audit check accepted only IMPORT_COMPLETED; retain all old events. */
IF COL_LENGTH('dbo.audit_events', 'actor_user_id') IS NULL
 ALTER TABLE dbo.audit_events ADD actor_user_id INT NULL;
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_audit_actor')
 ALTER TABLE dbo.audit_events ADD CONSTRAINT fk_audit_actor FOREIGN KEY (actor_user_id) REFERENCES dbo.users(id);
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_audit_events_type' AND parent_object_id = OBJECT_ID('dbo.audit_events'))
 ALTER TABLE dbo.audit_events DROP CONSTRAINT ck_audit_events_type;
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.audit_events') AND name='import_batch_id' AND is_nullable=0)
 ALTER TABLE dbo.audit_events ALTER COLUMN import_batch_id INT NULL;
ALTER TABLE dbo.audit_events ADD CONSTRAINT ck_audit_events_type
 CHECK (event_type IN ('IMPORT_COMPLETED','TICKET_CREATED','TICKET_UPDATED','TICKET_ASSIGNED','TICKET_NOTE','ASSET_CREATED','ASSET_UPDATED','ASSET_ASSIGNED','ASSET_RETURNED','USER_CREATED','USER_UPDATED'));
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_audit_events_actor' AND object_id = OBJECT_ID('dbo.audit_events'))
 CREATE INDEX ix_audit_events_actor ON dbo.audit_events(actor_user_id);

COMMIT TRANSACTION;
GO
SELECT (SELECT COUNT(*) FROM dbo.claims) AS existing_claims,
       (SELECT COUNT(*) FROM dbo.audit_events WHERE event_type='IMPORT_COMPLETED') AS original_import_events,
       (SELECT COUNT(*) FROM dbo.users) AS new_users;
GO
