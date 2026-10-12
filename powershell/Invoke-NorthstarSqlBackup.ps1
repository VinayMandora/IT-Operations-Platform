# Safe Windows scheduled-backup entrypoint. Preview by default.
# Only executes an approved, fixed local SQL backup SQL file with explicit -Execute.
[CmdletBinding()]
param(
    [string]$Server = '.\SQLEXPRESS',
    [switch]$Execute
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ScriptFile = Join-Path $ProjectRoot 'scripts\11_sqlserver_full_backup.sql'
$BackupFolder = 'C:\NorthstarLabBackups'
if (-not $Execute) {
    Write-Host 'DRY RUN: NO backup executed. Approved source DB: ClaimsITOpsDemo'
    Write-Host "Would use sqlcmd -S $Server -E -b -i $ScriptFile"
    Write-Host "SQL Server service must have write permissions on $BackupFolder"
    exit 0
}
if ($Server -notin @('.\SQLEXPRESS', 'localhost\SQLEXPRESS')) {
    throw 'Only the local SQL Express instance is permitted by this demonstration script.'
}
if (-not (Test-Path $BackupFolder -PathType Container)) {
    throw "Create $BackupFolder on the SQL Server computer and grant service access first."
}
$sqlcmd = Get-Command sqlcmd -ErrorAction Stop
Write-Host 'Starting explicitly authorised LOCAL SQL Server full backup with CHECKSUM...'
& ($sqlcmd.Source) -S $Server -E -b -i $ScriptFile
if ($LASTEXITCODE -ne 0) {throw "sqlcmd backup/verification failed; exit code $LASTEXITCODE"}
Write-Host 'Backup and RESTORE VERIFYONLY succeeded; check dbo.backup_jobs in SSMS.'
