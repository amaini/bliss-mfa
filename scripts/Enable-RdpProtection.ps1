[CmdletBinding()]
param([string]$Root='C:\BlissMFA', [string]$ProtectedUser,
      [switch]$RecoveryConfirmed, [switch]$Disable)
$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run as Administrator.' }
$key='Registry::HKEY_CLASSES_ROOT\CLSID\{FCEFDFAB-B0A1-4C4D-8B2B-4FF4E0A3D978}'
if ($Disable) {
    foreach ($name in @('cpus_logon','cpus_unlock','cpus_credui')) { Set-ItemProperty $key -Name $name -Value '3d' }
    Write-Output 'RDP MFA enforcement disabled. Enrollments remain available.'
    return
}
if (!$RecoveryConfirmed) { throw 'Keep a tested recovery-administrator session or console available, then use -RecoveryConfirmed.' }
if (!$ProtectedUser) { throw 'Specify the enrolled Windows account with -ProtectedUser.' }
$provider=Get-ItemProperty $key
if (!$provider.excluded_account) { throw 'Configure a recovery-administrator exception first.' }
$user=Get-LocalUser -Name $ProtectedUser
if (!$user.Enabled) { throw 'Windows account is disabled.' }
if ($provider.excluded_account.Split('\')[-1] -ieq $ProtectedUser) { throw 'Use an account other than the recovery administrator.' }
& (Join-Path $Root 'python\python.exe') (Join-Path $Root 'bliss-mfa\scripts\provider-readiness.py') --root $Root --username $ProtectedUser
if ($LASTEXITCODE -ne 0) { throw 'Licensed account readiness failed.' }
$config=Get-Content (Join-Path $Root 'bliss-mfa\.local\engine\config.json') -Raw | ConvertFrom-Json
$secure=Read-Host 'Enter a fresh authenticator code for the enrolled account' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $code=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ($code -notmatch '^\d{6}$') { throw 'Enter a six-digit authenticator code.' }
    if ($code -eq '000000') { throw 'Wait for the next authenticator code, then retry.' }
    $client=Join-Path $provider.multiOTPPath 'multiotp.exe'
    # Consume the code once through the same installed client used by Windows.
    & $client -cp ('-base-dir='+(Join-Path $Root 'provider-validation')+'\') '-server-cache-level=0' '-server-timeout=2' ('-server-url=https://127.0.0.1:'+$config.auth_port+'/auth') ('-server-secret='+$config.native_shared_secret) $ProtectedUser $code *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Native verification failed. Wait for a new authenticator code and retry.' }
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $code=$null
}
Set-ItemProperty $key -Name cpus_logon -Value '1e'
Set-ItemProperty $key -Name cpus_unlock -Value '1e'
Set-ItemProperty $key -Name cpus_credui -Value '3d'
Write-Output 'RDP logon and unlock protection enabled. Wait for a new authenticator code, then perform the RDP test in the portal checklist.'
