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
    $rules = @(Get-NetFirewallRule -Name 'WINRM-HTTP-In-TCP*' -ErrorAction Stop)
    if (!$rules.Count) { throw 'No WinRM HTTP firewall rules found; inspect the VM configuration.' }
    $rules | Set-NetFirewallRule -RemoteAddress $ControllerTailscaleAddress -LocalAddress $ExpectedTailscaleAddress
    # NTLM/Kerberos message encryption remains mandatory. No Basic authentication.
    Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $false
    Set-Item WSMan:\localhost\Service\Auth\Basic -Value $false
    $inventory.WinRMConfiguredByThisScript = $true
}
$inventory | ConvertTo-Json
