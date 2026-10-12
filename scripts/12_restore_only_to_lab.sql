/* DANGER GUARDS: creates ONLY ClaimsITOpsRestoreLab; NEVER changes ClaimsITOpsDemo.
   SSMS only. Require source + lab target on same isolated SQL Server instance.
   Inspect RESTORE FILELISTONLY output and confirm source file layout before executing.
   Script assumes a standard one-data-file/one-log-file SQL Server Express database. */
USE master;
GO
IF DB_ID(N'ClaimsITOpsDemo') IS NULL THROW 51201, 'Source DB not found', 1;
IF DB_ID(N'ClaimsITOpsRestoreLab') IS NOT NULL
 THROW 51202, 'Restore LAB database already exists: never overwrite it automatically', 1;
IF (SELECT COUNT(*) FROM sys.master_files WHERE database_id=DB_ID(N'ClaimsITOpsDemo')) <> 2
 THROW 51203, 'Unexpected SQL file layout; inspect manually; lab restore not attempted', 1;
RESTORE VERIFYONLY FROM DISK=N'C:\NorthstarLabBackups\ClaimsITOpsDemo_full.bak' WITH CHECKSUM;
GO
DECLARE @data SYSNAME, @log SYSNAME, @sql NVARCHAR(MAX);
SELECT @data=name FROM sys.master_files WHERE database_id=DB_ID(N'ClaimsITOpsDemo') AND type=0;
SELECT @log=name FROM sys.master_files WHERE database_id=DB_ID(N'ClaimsITOpsDemo') AND type=1;
IF @data IS NULL OR @log IS NULL THROW 51204, 'Cannot resolve logical file names', 1;
-- RESTORE FILELISTONLY is the authoritative check of names inside the backup.
RESTORE FILELISTONLY FROM DISK=N'C:\NorthstarLabBackups\ClaimsITOpsDemo_full.bak';
PRINT 'Compare logical file names above against the current source before authorising restore.';
-- TWO-STAGE EXPLICIT GATE: default execution stops after inspection and does not restore.
-- Only set 1 yourself in an APPROVED isolated lab after checking RESTORE FILELISTONLY.
DECLARE @LabRestoreConfirmed BIT = 0;
IF @LabRestoreConfirmed <> 1
 THROW 51206, 'Safety gate: review RESTORE FILELISTONLY, then set @LabRestoreConfirmed = 1 for the approved lab only', 1;
-- Restore uses unique file paths; target database name is a literal lab-only name.
SET @sql=N'RESTORE DATABASE [ClaimsITOpsRestoreLab] FROM DISK=N''C:\NorthstarLabBackups\ClaimsITOpsDemo_full.bak'' WITH '
 +N'MOVE '+QUOTENAME(@data,'''')+N' TO N''C:\NorthstarLabBackups\ClaimsITOpsRestoreLab.mdf'', '
 +N'MOVE '+QUOTENAME(@log,'''')+N' TO N''C:\NorthstarLabBackups\ClaimsITOpsRestoreLab_log.ldf'', '
 +N'RECOVERY, CHECKSUM, STATS=10;';
IF DB_ID(N'ClaimsITOpsRestoreLab') IS NOT NULL THROW 51205, 'Lab target unexpectedly exists', 1;
EXEC sys.sp_executesql @sql;
SELECT name,state_desc FROM sys.databases WHERE name IN (N'ClaimsITOpsDemo',N'ClaimsITOpsRestoreLab');
GO
