#requires -Version 5.1
<#
.SYNOPSIS
  Northstar Claims Active Directory rehearsal. DRY-RUN BY DEFAULT.
.EXAMPLE
  .\powershell\Invoke-NorthstarAD.ps1 -PlanPath .\sample_data\task3_ad_plan.json
.EXAMPLE
  .\powershell\Invoke-NorthstarAD.ps1 -PlanPath .\sample_data\task3_ad_plan.json -Action InspectUser
.NOTES
  Lab-only: -LabLive loads RSAT; modifying cmdlets use -WhatIf unless -CommitLabChanges
  AND NORTHSTAR_AD_LAB_ALLOWED=YES and interactive confirmation.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$PlanPath,
    [ValidateSet('PrepareAccount','InspectUser','InspectGroups','DisableAccount')][string]$Action='PrepareAccount',
    [switch]$LabLive,
    [switch]$CommitLabChanges,
    [string]$LabServer='dc1.northstar.lab',
    [string]$LabOU='OU=LabUsers,DC=northstar,DC=lab'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($plan.domain -ne 'northstar.lab' -or $plan.samAccountName -notmatch '^nc[0-9]{6}$') {
    throw 'Plan must target the Northstar fictional AD lab domain and a generated nc user.'
}
if ($LabServer -ne 'dc1.northstar.lab' -or $LabOU -ne 'OU=LabUsers,DC=northstar,DC=lab') {
    throw 'Non-lab target refused. This script only supports the isolated northstar.lab example.'
}
foreach ($group in $plan.groups) {
    if ($group -notin @('SG-Claims-Read','SG-Claims-Write','SG-Operations-Read','SG-Finance-Read','SG-HR-Read','SG-IT-Helpdesk')) {
        throw "Unapproved lab group $group"
    }
}
if (-not $LabLive) {
    Write-Host 'DRY RUN. No AD module, network connection or account changes.' -ForegroundColor Cyan
    [pscustomobject]@{Mode='DryRun';Action=$Action;User=$plan.samAccountName;Groups=$plan.groups;Target=$LabServer} | Format-List
    switch ($Action) {
        'PrepareAccount' { Write-Host "WOULD: New-ADUser -Name '$($plan.name)' -SamAccountName '$($plan.samAccountName)' -Server '$LabServer'";
                           foreach ($g in $plan.groups) { Write-Host "WOULD: Add-ADGroupMember -Identity '$g' -Members '$($plan.samAccountName)'" } }
        'InspectUser' { Write-Host "WOULD: Get-ADUser -Identity '$($plan.samAccountName)'" }
        'InspectGroups' { foreach ($g in $plan.groups) { Write-Host "WOULD: Get-ADGroupMember -Identity '$g'" } }
        'DisableAccount' { Write-Host "WOULD: Disable-ADAccount -Identity '$($plan.samAccountName)'" }
    }
    exit 0
}
Import-Module ActiveDirectory -ErrorAction Stop
if ($CommitLabChanges) {
    if ($env:NORTHSTAR_AD_LAB_ALLOWED -ne 'YES') { throw 'Set NORTHSTAR_AD_LAB_ALLOWED=YES inside the isolated lab only.' }
    $ack = Read-Host 'Type NORTHSTAR LAB ONLY to commit changes to your isolated domain'
    if ($ack -cne 'NORTHSTAR LAB ONLY') { throw 'Approval phrase mismatch; no changes made.' }
}
$whatIf = -not $CommitLabChanges
switch ($Action) {
    'InspectUser' { Get-ADUser -Identity $plan.samAccountName -Server $LabServer -Properties Enabled,EmailAddress,MemberOf |
                   Select-Object SamAccountName,Enabled,EmailAddress,MemberOf }
    'InspectGroups' { foreach ($g in $plan.groups) {
                         Get-ADGroupMember -Identity $g -Server $LabServer | Select-Object @{n='Group';e={$g}},Name,SamAccountName
                     } }
    'PrepareAccount' {
        if ($whatIf) {
            Write-Host 'Lab connection enabled but changes guarded by -WhatIf.'
            New-ADUser -Name $plan.name -SamAccountName $plan.samAccountName -UserPrincipalName "$($plan.samAccountName)@northstar.lab" `
              -EmailAddress $plan.email -Department $plan.department -Title $plan.title -Path $LabOU `
              -Server $LabServer -Enabled:$false -WhatIf
            foreach ($g in $plan.groups) { Add-ADGroupMember -Identity $g -Members $plan.samAccountName -Server $LabServer -WhatIf }
        } else {
            $password = Read-Host 'Temporary LAB-only password' -AsSecureString
            New-ADUser -Name $plan.name -SamAccountName $plan.samAccountName -UserPrincipalName "$($plan.samAccountName)@northstar.lab" `
              -EmailAddress $plan.email -Department $plan.department -Title $plan.title -Path $LabOU `
              -Server $LabServer -Enabled:$true -AccountPassword $password -ChangePasswordAtLogon $true -ErrorAction Stop
            foreach ($g in $plan.groups) { Add-ADGroupMember -Identity $g -Members $plan.samAccountName -Server $LabServer -ErrorAction Stop }
            Get-ADUser -Identity $plan.samAccountName -Server $LabServer | Select-Object Name,SamAccountName,Enabled
        }
    }
    'DisableAccount' {
        Disable-ADAccount -Identity $plan.samAccountName -Server $LabServer -WhatIf:$whatIf -ErrorAction Stop
    }
}
