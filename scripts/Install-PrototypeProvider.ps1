# Stage the provider disabled. Enable enforcement only after native client tests.
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'WIN-10VM-ASUS') { throw 'Wrong disposable VM.' }
$root = 'C:\BlissMFA'
$msi = "$root\installers\multiOTPCredentialProviderInstaller.msi"
if ((Get-AuthenticodeSignature $msi).Status -ne 'Valid') { throw 'Provider installer signature invalid.' }
$providerKey = 'Registry::HKEY_CLASSES_ROOT\CLSID\{FCEFDFAB-B0A1-4C4D-8B2B-4FF4E0A3D978}'
if (Test-Path $providerKey) { throw 'Provider already installed; inspect before upgrading.' }
$args = @('/i', ('"' + $msi + '"'), '/qn', '/norestart', '/L*v', 'C:\BlissMFA\provider-install.log',
    'CPUS_LOGON=3d', 'CPUS_UNLOCK=3d', 'CPUS_CREDUI=3d', 'MULTIOTP_CACHE=0',
    'MULTIOTP_TWO_STEP_SEND_PASSWORD=0', 'MULTIOTP_URL=https://127.0.0.1:18443/auth')
$install = Start-Process msiexec.exe -ArgumentList $args -Wait -PassThru -WindowStyle Hidden
if ($install.ExitCode -notin @(0,3010)) { throw "Provider installation failed: $($install.ExitCode)" }
$config = Get-Content "$root\bliss-mfa\.local\engine\config.json" -Raw | ConvertFrom-Json
$recoveryAccount = [Security.Principal.WindowsIdentity]::GetCurrent().Name
foreach ($setting in @{
    cpus_logon='3d';cpus_unlock='3d';cpus_credui='3d';
    multiOTPServers='https://127.0.0.1:18443/auth';multiOTPSharedSecret=$config.native_shared_secret;
    excluded_account=$recoveryAccount;login_text='Bliss MFA prototype'
}.GetEnumerator()) {
    New-ItemProperty -Path $providerKey -Name $setting.Key -Value $setting.Value -PropertyType String -Force | Out-Null
}
foreach ($setting in @{
    multiOTPCacheEnabled=0;multiOTPTimeoutUnlock=0;multiOTPWithout2FA=0;
    two_step_send_password=0;two_step_send_empty_password=0;multiOTPDisplaySmsLink=0;multiOTPDisplayEmailLink=0
}.GetEnumerator()) {
    New-ItemProperty -Path $providerKey -Name $setting.Key -Value $setting.Value -PropertyType DWord -Force | Out-Null
}
$provider = Get-ItemProperty $providerKey
[ordered]@{ExitCode=$install.ExitCode;ProviderPath=$provider.multiOTPPath;Logon=$provider.cpus_logon;Unlock=$provider.cpus_unlock;RecoveryAccount=$recoveryAccount;Cache=$provider.multiOTPCacheEnabled} | ConvertTo-Json
Get-ChildItem -LiteralPath $provider.multiOTPPath -Recurse -File | Where-Object Name -in @('multiotp.exe','multiotp.windows.php','php.ini','php.exe') | Select-Object FullName,Length | ConvertTo-Json
