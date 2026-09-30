# Run manually inside the disposable Windows VM. Default is read-only inventory.
[CmdletBinding()]
param(
    [switch]$ConfigureWinRM,
    [string]$ExpectedComputerName,
    [string]$ExpectedTailscaleAddress = '100.83.112.5',
    [string]$ControllerTailscaleAddress = '100.68.167.45',
    [switch]$RecoveryConfirmed
)
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$addresses = @(Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress)
$inventory = [ordered]@{
    ComputerName = $env:COMPUTERNAME
    Windows = $os.Caption
    Version = $os.Version
    Build = $os.BuildNumber
    ExpectedTailscaleAddressPresent = $addresses -contains $ExpectedTailscaleAddress
    ExistingProviderRegistration = Test-Path 'Registry::HKEY_CLASSES_ROOT\CLSID\{FCEFDFAB-B0A1-4C4D-8B2B-4FF4E0A3D978}'
    WinRMConfiguredByThisScript = $false
}
if ($ConfigureWinRM) {
    if (!$ExpectedComputerName -or $ExpectedComputerName -ne $env:COMPUTERNAME) {
        throw 'ExpectedComputerName must match the disposable VM inventory exactly.'
    }
    if (!$RecoveryConfirmed) {
        throw 'Confirm an independent console/checkpoint recovery route before configuring the VM.'
    }
    if ($addresses -notcontains $ExpectedTailscaleAddress) {
        throw 'This computer does not own the expected disposable VM Tailscale address.'
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run inside the disposable VM in an Administrator PowerShell.'
    }
    Enable-PSRemoting -Force -SkipNetworkProfileCheck
    Set-Service -Name WinRM -StartupType Automatic
    Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\WinRM' -Name DelayedAutoStart -Value 0
    $rules = @(Get-NetFirewallRule -Name 'WINRM-HTTP-In-TCP*' -ErrorAction Stop)
    if (!$rules.Count) { throw 'No WinRM HTTP firewall rules found; inspect the VM configuration.' }
    $rules | Set-NetFirewallRule -Enabled True -Profile Any -RemoteAddress $ControllerTailscaleAddress -LocalAddress $ExpectedTailscaleAddress
    # NTLM/Kerberos message encryption remains mandatory. No Basic authentication.
    # Avoid redundant writes: changing the service can re-run a Public-network
    # check even when the secure default is already in effect.
    $serviceConfig = (& winrm.cmd get winrm/config/service) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to read WinRM service settings.' }
    if ($serviceConfig -notmatch '(?m)^\s*AllowUnencrypted\s*=\s*false\b') {
        & winrm.cmd set winrm/config/service '@{AllowUnencrypted="false"}'
        if ($LASTEXITCODE -ne 0) { throw 'Failed to require WinRM message encryption.' }
    }
    if ($serviceConfig -notmatch '(?m)^\s*Basic\s*=\s*false\b') {
        & winrm.cmd set winrm/config/service/auth '@{Basic="false"}'
        if ($LASTEXITCODE -ne 0) { throw 'Failed to disable WinRM Basic authentication.' }
    }
    $verifiedConfig = (& winrm.cmd get winrm/config/service) -join "`n"
    if ($LASTEXITCODE -ne 0 -or
        $verifiedConfig -notmatch '(?m)^\s*AllowUnencrypted\s*=\s*false\b' -or
        $verifiedConfig -notmatch '(?m)^\s*Basic\s*=\s*false\b') {
        throw 'WinRM secure settings could not be verified.'
    }
    $inventory.WinRMConfiguredByThisScript = $true
}
$inventory | ConvertTo-Json
