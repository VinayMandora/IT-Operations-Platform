<#
 Runs Task 4 against the LOCAL FastAPI mock CRM only.
 Requires sample_data/task4_demo_claims.csv to be imported first.
 Prompts for the demonstration Admin password; does not write secrets to disk.
#>
param([string]$BaseUrl='http://127.0.0.1:8000', [string]$Username='admin')
$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')
if ($BaseUrl -ne 'http://127.0.0.1:8000' -and $BaseUrl -ne 'http://localhost:8000') {
    throw 'Demonstration is restricted to the local FastAPI server on port 8000.'
}

$secure = Read-Host 'Local demonstration Admin password' -AsSecureString
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $password = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
$webSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
function Call-Api([string]$Path, [string]$Method='GET', [object]$Payload=$null) {
    $args = @{ Uri=($BaseUrl+$Path); Method=$Method; WebSession=$webSession; ErrorAction='Stop' }
    if ($Method -ne 'GET') { $args['Headers'] = $script:headers }
    if ($null -ne $Payload) {
        $args['ContentType'] = 'application/json'
        $args['Body'] = ConvertTo-Json -InputObject $Payload -Compress -Depth 6
    }
    return Invoke-RestMethod @args
}
try {
    $login = Invoke-RestMethod -Uri ($BaseUrl+'/api/auth/login') -Method POST `
      -WebSession $webSession -ContentType 'application/json' `
      -Body (ConvertTo-Json @{ username=$Username; password=$password } -Compress)
} finally { $password = $null }
if ($login.user.role -ne 'Admin') { throw 'Use a Task 2 administrator account.' }
$script:headers = @{ 'X-CSRF-Token' = $login.csrf_token }
$claim = Call-Api '/api/crm/claims/NCL-009999'
if ($claim.stage -ne 'New') {
    throw "Demo claim NCL-009999 has stage $($claim.stage). Use a new fictional claim ID for another full run."
}
$uid = [Guid]::NewGuid().ToString('N')
Write-Host 'Step 1: Pull the fictional record from mock Zoho CRM'
$pull = Call-Api '/api/crm/claims/NCL-009999/sync' 'POST' @{ operation_key=($uid+'-pull') }
Write-Host "CRM integration: $($pull.status)"

function Send-Event([string]$Name) {
    $key = $uid+'-'+$Name
    $result = Call-Api '/api/workflows/events' 'POST' @{
       claim_id='NCL-009999'; event_type=$Name; event_key=$key
    }
    Write-Host "$Name => $(($result.results | ForEach-Object { $_.status }) -join ', ')"
    return $result
}
Write-Host 'Step 2: Claim submission and assignment'
$first = Send-Event 'submitted'
$replay = Call-Api '/api/workflows/events' 'POST' @{
  claim_id='NCL-009999'; event_type='submitted'; event_key=($uid+'-submitted')
}
Write-Host "Duplicate event recognised: $($replay.results[0].replayed)"
Write-Host 'Step 3: Evidence required'
$second = Send-Event 'missing_documents'
Write-Host 'Step 4: Evidence received'
$third = Send-Event 'evidence_received'
Write-Host 'Step 5: Resolve the fictional claim'
$fourth = Send-Event 'resolved'
$push = Call-Api '/api/crm/claims/NCL-009999/push' 'POST' @{operation_key=($uid+'-push')}
Write-Host "CRM mock push: $($push.status)"
$completed = Call-Api '/api/crm/claims/NCL-009999'
Write-Host "Final stage: $($completed.stage); original claim status: $($completed.claim_status)"
Write-Host 'Step 6: Create a deliberate failed workflow on separate demo claim NCL-009998'
$rule = Call-Api '/api/workflows/rules' 'POST' @{
   name=('Troubleshooting exercise '+$uid.Substring(0,8)); event_type='submitted'; action_type='demo_fail'
}
$bad = Call-Api '/api/workflows/events' 'POST' @{
  claim_id='NCL-009998'; event_type='submitted'; event_key=($uid+'-failure')
}
$failed = @($bad.results | Where-Object {$_.status -eq 'Failed'}) | Select-Object -First 1
if ($null -eq $failed) { throw 'Expected an intentional failed workflow event.' }
Write-Host "Failed workflow #$($failed.execution_id); support ticket #$($failed.support_ticket_id)"
Write-Host 'Step 7: Fix configured action, then retry'
$edit = Call-Api ('/api/workflows/rules/'+$rule.id) 'PATCH' @{action_type='evidence_required'}
$retry = Call-Api ('/api/workflows/executions/'+$failed.execution_id+'/retry') 'POST'
Write-Host "Retry status: $($retry.status); retry count: $($retry.retry_count)"
Write-Host 'Task 4 demonstration complete: open /claims-management and /workflow-logs.'
