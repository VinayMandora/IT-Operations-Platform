/* Local lab ONLY. Run in SSMS/sqlcmd AFTER making C:\NorthstarLabBackups on
   the SQL Server machine and granting the SQL Server SERVICE identity write access.
   Replaces only the named .bak FILE; it does NOT overwrite any database.
   BACKUP WITH CHECKSUM + RESTORE VERIFYONLY checks media consistency (not a full restore). */
USE master;
GO
SET NOCOUNT ON;
IF DB_ID(N'ClaimsITOpsDemo') IS NULL THROW 51101, 'Source database missing', 1;
IF OBJECT_ID(N'ClaimsITOpsDemo.dbo.backup_jobs','U') IS NULL THROW 51102, 'Run Task 5 migration first', 1;
BEGIN TRY
 BACKUP DATABASE [ClaimsITOpsDemo]
 TO DISK = N'C:\NorthstarLabBackups\ClaimsITOpsDemo_full.bak'
 WITH INIT, CHECKSUM, NAME = N'Northstar Claims Task 5 lab full backup', STATS = 10;
 RESTORE VERIFYONLY FROM DISK = N'C:\NorthstarLabBackups\ClaimsITOpsDemo_full.bak' WITH CHECKSUM;
 INSERT INTO ClaimsITOpsDemo.dbo.backup_jobs
 (backup_type,result,location,file_size,sha256,verified_at,failure_reason,ticket_id,actor_user_id,created_at)
 VALUES ('SQLFull','Success',N'C:\NorthstarLabBackups\ClaimsITOpsDemo_full.bak',NULL,NULL,GETUTCDATE(),NULL,NULL,NULL,GETUTCDATE());
 PRINT 'SQL full backup complete and RESTORE VERIFYONLY succeeded.';
END TRY
BEGIN CATCH
 DECLARE @error NVARCHAR(1000)=ERROR_MESSAGE();
 INSERT INTO ClaimsITOpsDemo.dbo.backup_jobs
 (backup_type,result,location,file_size,sha256,verified_at,failure_reason,ticket_id,actor_user_id,created_at)
 VALUES ('SQLFull','Failed',N'C:\NorthstarLabBackups\ClaimsITOpsDemo_full.bak',NULL,NULL,NULL,@error,NULL,NULL,GETUTCDATE());
 THROW;
END CATCH;
GO
