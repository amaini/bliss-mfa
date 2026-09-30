$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -ne 'WIN-10VM-ASUS') { throw 'Wrong disposable VM.' }
$data=Get-Content 'C:\BlissMFA\prototype-test-account.json' -Raw | ConvertFrom-Json
if ($data.username -ne 'bliss_proto_test') { throw 'Unexpected test identity.' }
if (Get-LocalUser -Name $data.username -ErrorAction SilentlyContinue) { throw 'Test Windows account already exists.' }
$password=ConvertTo-SecureString $data.windows_password -AsPlainText -Force
New-LocalUser -Name $data.username -Password $password -Description 'Disposable Bliss MFA RDP acceptance account' -AccountNeverExpires | Out-Null
$rdpGroup=Get-LocalGroup -SID 'S-1-5-32-555'
Add-LocalGroupMember -Group $rdpGroup -Member $data.username
$key='Registry::HKEY_CLASSES_ROOT\CLSID\{FCEFDFAB-B0A1-4C4D-8B2B-4FF4E0A3D978}'
$settings=Get-ItemProperty $key
$current=[Security.Principal.WindowsIdentity]::GetCurrent().Name
if ($settings.excluded_account -ne $current) { throw 'Existing administrator recovery exception is missing.' }
if ($settings.multiOTPCacheEnabled -ne 0) { throw 'Offline caching must be disabled.' }
# The administrator's normal desktop token can read only the enrollment page;
# engine state and configuration continue to require elevation.
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe 'C:\BlissMFA\Prototype-Enrollment.html' /grant:r ('*'+$sid+':R') | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not grant operator access to enrollment page.' }
# Local console and CredUI keep their normal sign-in path. RDP requires this provider.
Set-ItemProperty $key -Name cpus_logon -Value '1e'
Set-ItemProperty $key -Name cpus_unlock -Value '1e'
Set-ItemProperty $key -Name cpus_credui -Value '3d'
$updated=Get-ItemProperty $key
[ordered]@{TestAccount=$data.username;Enabled=(Get-LocalUser $data.username).Enabled;RDPGroup=$rdpGroup.Name;Logon=$updated.cpus_logon;Unlock=$updated.cpus_unlock;CredUI=$updated.cpus_credui;RecoveryAccount=$updated.excluded_account} | ConvertTo-Json
