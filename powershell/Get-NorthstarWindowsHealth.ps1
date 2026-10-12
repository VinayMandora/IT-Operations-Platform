# Standalone read-only Windows workstation health report. Does not change Defender.
$ErrorActionPreference = 'Continue'
$mp = $null
try { $mp = Get-MpComputerStatus -ErrorAction Stop } catch { Write-Warning 'Defender data unavailable on this machine.' }
$os = Get-CimInstance Win32_OperatingSystem
$drive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
[pscustomobject]@{
    Computer = $env:COMPUTERNAME
    OperatingSystem = $os.Caption
    AntivirusEnabled = if ($mp) { $mp.AntivirusEnabled } else { $null }
    RealTimeProtectionEnabled = if ($mp) { $mp.RealTimeProtectionEnabled } else { $null }
    SignatureAgeDays = if ($mp -and $mp.AntivirusSignatureLastUpdated) {
        [int]((Get-Date) - $mp.AntivirusSignatureLastUpdated).TotalDays
    } else { $null }
    DiskFreeGB = if ($drive) { [math]::Round($drive.FreeSpace / 1GB, 2) } else { $null }
    DiskTotalGB = if ($drive) { [math]::Round($drive.Size / 1GB, 2) } else { $null }
} | Format-List
