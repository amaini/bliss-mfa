# Install the signed Windows provider with enforcement disabled until enrollment.
[CmdletBinding()]
param([string]$Root='C:\BlissMFA', [string]$RecoveryAccount=[Security.Principal.WindowsIdentity]::GetCurrent().Name)
$ErrorActionPreference='Stop'
$key='Registry::HKEY_CLASSES_ROOT\CLSID\{FCEFDFAB-B0A1-4C4D-8B2B-4FF4E0A3D978}'
if (Test-Path $key) { throw 'A credential provider is already installed; use the upgrade workflow.' }
$msi=Join-Path $Root 'installers\multiOTPCredentialProviderInstaller.msi'
if ((Get-FileHash $msi -Algorithm SHA256).Hash -ne '21FE0897C0056CFADD9FC741AFFB77C0CC7C87C86022A51A7CB9F7AB1C65CBD5' -or
    (Get-AuthenticodeSignature $msi).Status -ne 'Valid') { throw 'Provider release integrity or signature failed.' }
$account=New-Object Security.Principal.NTAccount($RecoveryAccount)
$null=$account.Translate([Security.Principal.SecurityIdentifier])
$log=Join-Path $Root 'provider-install.log'
$arguments=@('/i',('"'+$msi+'"'),'/qn','/norestart','/L*v',('"'+$log+'"'),
    'CPUS_LOGON=3d','CPUS_UNLOCK=3d','CPUS_CREDUI=3d','MULTIOTP_CACHE=0',
    'MULTIOTP_TWO_STEP_SEND_PASSWORD=0','MULTIOTP_URL=https://127.0.0.1:18443/auth')
$install=Start-Process msiexec.exe -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
if ($install.ExitCode -notin @(0,3010)) { throw 'Provider installation failed.' }
$config=Get-Content (Join-Path $Root 'bliss-mfa\.local\engine\config.json') -Raw | ConvertFrom-Json
$provider=Get-ItemProperty $key
$providerRoot=$provider.multiOTPPath.TrimEnd('\')
# Stage only runs on a freshly installed stock provider: keep each installation's recovery
# points separate so files retained from an earlier install never block a reinstall.
$backup=Join-Path $Root ('provider-backup\'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$script=Join-Path $providerRoot 'php\multiotp.windows.php'
$ini=Join-Path $providerRoot 'php\php.ini'
Copy-Item -LiteralPath $script -Destination (Join-Path $backup 'multiotp.windows.before-tls.php')
Copy-Item -LiteralPath $ini -Destination (Join-Path $backup 'php.before-tls.ini')
$text=[IO.File]::ReadAllText($script)
$end=$text.IndexOf("'disable_compression'",$text.IndexOf('_default_ssl_context = array('))
if ($end -lt 0) { throw 'Unexpected native TLS context.' }
$regex=[regex]::new("('verify_peer(?:_name)?'\s*=>\s*)false")
$prefix=$text.Substring(0,$end)
if ($regex.Matches($prefix).Count -ne 2) { throw 'Unexpected native TLS defaults.' }
[IO.File]::WriteAllText($script,$regex.Replace($prefix,'${1}true')+$text.Substring($end),(New-Object Text.UTF8Encoding($false)))
$ca=Join-Path $providerRoot 'php\bliss-engine-ca.pem'
Copy-Item -LiteralPath $config.certificate_file -Destination $ca
[IO.File]::AppendAllText($ini,"`r`n; Bliss: pin the local engine certificate.`r`nopenssl.cafile=`"$ca`"`r`n",(New-Object Text.UTF8Encoding($false)))
& (Join-Path $providerRoot 'php\php.exe') -l $script
if ($LASTEXITCODE -ne 0) { throw 'Provider PHP syntax check failed.' }
& (Join-Path $Root 'bliss-mfa\scripts\Patch-ProviderHttpFraming.ps1') -ProviderRoot $providerRoot -BackupRoot $backup
foreach ($setting in @{
    cpus_logon='3d';cpus_unlock='3d';cpus_credui='3d';
    multiOTPServers=('https://127.0.0.1:'+$config.auth_port+'/auth');
    multiOTPSharedSecret=$config.native_shared_secret;excluded_account=$RecoveryAccount;login_text='Bliss MFA'
}.GetEnumerator()) {
    New-ItemProperty $key -Name $setting.Key -Value $setting.Value -PropertyType String -Force | Out-Null
}
foreach ($setting in @{
    multiOTPCacheEnabled=0;multiOTPTimeoutUnlock=0;multiOTPWithout2FA=0;
    two_step_send_password=0;two_step_send_empty_password=0;multiOTPDisplaySmsLink=0;multiOTPDisplayEmailLink=0
}.GetEnumerator()) {
    New-ItemProperty $key -Name $setting.Key -Value $setting.Value -PropertyType DWord -Force | Out-Null
}
Write-Output 'Windows provider staged. RDP enforcement remains disabled until licensed enrollment and a fresh-code verification.'
