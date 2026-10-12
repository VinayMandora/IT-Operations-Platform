-- Run in SSMS connected to .\SQLEXPRESS using Windows Authentication.
-- Requires CREATE DATABASE permission (local sysadmin is sufficient).
USE master;
GO
IF DB_ID(N'ClaimsITOpsDemo') IS NULL
BEGIN
    CREATE DATABASE ClaimsITOpsDemo;
END;
GO
SELECT name, state_desc
FROM sys.databases
WHERE name = N'ClaimsITOpsDemo';
GO
-- Application tables are then created from SQLAlchemy models:
-- python -m scripts.init_schema
