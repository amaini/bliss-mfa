[CmdletBinding(SupportsShouldProcess=$true)]
param()
$ErrorActionPreference='Stop'
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    if ($WhatIfPreference) { throw 'Run the uninstall preview as Administrator.' }
    $p=Start-Process powershell.exe -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "'+$PSCommandPath+'"') -Verb RunAs -WindowStyle Normal -Wait -PassThru
    exit $p.ExitCode
}
try {
    $metadata=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'installation.json') -Raw | ConvertFrom-Json
    $rootPath=(Resolve-Path -LiteralPath $metadata.Root).Path.TrimEnd('\')
    if (!(Test-Path -LiteralPath (Join-Path $rootPath 'bliss-mfa\.local\engine\appliance.json')) -or !(Test-Path -LiteralPath (Join-Path $rootPath 'manifest.json'))) { throw 'Installation identity checks failed.' }
    if (!$PSCmdlet.ShouldProcess($rootPath,'Remove MFA protection, service and application binaries; preserve private configuration and backups')) { return }
    if ((Read-Host 'Uninstall removes RDP MFA protection. Private data is retained. Type UNINSTALL to continue') -cne 'UNINSTALL') { return }
    $updateTask=Get-ScheduledTask 'BlissMFA-Updates' -ErrorAction SilentlyContinue
    if ($updateTask) {
        if ($updateTask.State -eq 'Running') { throw 'An update is running; wait for it to finish before uninstalling.' }
        if ($updateTask.Actions.Execute -notlike ($metadata.ControlRoot+'\*')) { throw 'Updater task ownership mismatch.' }
        Unregister-ScheduledTask -InputObject $updateTask -Confirm:$false
    }
    $provider='Registry::HKEY_CLASSES_ROOT\CLSID\{FCEFDFAB-B0A1-4C4D-8B2B-4FF4E0A3D978}'
    if (Test-Path $provider) {
        if ((Get-ItemProperty $provider).login_text -ne 'Bliss MFA') { throw 'A different provider configuration exists; refusing removal.' }
        foreach ($name in @('cpus_logon','cpus_unlock','cpus_credui')) { Set-ItemProperty $provider -Name $name -Value '3d' }
        $msi=Join-Path $rootPath 'installers\multiOTPCredentialProviderInstaller.msi'
        if ((Get-FileHash -LiteralPath $msi).Hash -ne '21FE0897C0056CFADD9FC741AFFB77C0CC7C87C86022A51A7CB9F7AB1C65CBD5') { throw 'Provider uninstall package integrity failed.' }
        $p=Start-Process msiexec.exe -ArgumentList ('/x "'+$msi+'" /qn /norestart') -WindowStyle Hidden -Wait -PassThru
        if ($p.ExitCode -notin @(0,1605,3010)) { throw 'Provider removal failed; engine remains installed.' }
        if (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\{FCEFDFAB-B0A1-4C4D-8B2B-4FF4E0A3D978}') { throw 'Provider remains registered; engine remains installed.' }
    }
    $serviceExe=Join-Path $rootPath 'service\BlissMFAEngine.exe'
    if (Get-Service BlissMFAEngine -ErrorAction SilentlyContinue) {
        if ((Get-Service BlissMFAEngine).Status -ne 'Stopped') { & $serviceExe stop; if ($LASTEXITCODE -ne 0) { throw 'Service stop failed.' } }
        & $serviceExe uninstall
        if ($LASTEXITCODE -ne 0) { throw 'Service removal failed.' }
    }
    $task=Get-ScheduledTask 'BlissMFA-PrototypeEngine' -ErrorAction SilentlyContinue
    if ($task) { Unregister-ScheduledTask -InputObject $task -Confirm:$false }
    $certificate=Join-Path $rootPath 'bliss-mfa\.local\engine\engine-cert.pem'
    if (Test-Path -LiteralPath $certificate) {
        $cert=New-Object Security.Cryptography.X509Certificates.X509Certificate2($certificate)
        $certPath='Cert:\LocalMachine\Root\'+$cert.Thumbprint
        if (Test-Path $certPath) { Remove-Item -LiteralPath $certPath }
    }
    foreach ($relative in @('python','node','multiotp-engine','installers','service','bliss-mfa\apps','bliss-mfa\services','bliss-mfa\scripts','bliss-mfa\deployment','bliss-mfa\website')) {
        $target=[IO.Path]::GetFullPath((Join-Path $rootPath $relative))
        if (!$target.StartsWith($rootPath+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe removal path.' }
        if (Test-Path -LiteralPath $target) {
            if ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing removal of a linked directory.' }
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }
    $menu=Join-Path ([Environment]::GetFolderPath('CommonPrograms')) 'Bliss MFA'
    foreach ($file in @((Join-Path $menu 'Bliss MFA Portal.url'),(Join-Path $menu 'Uninstall Bliss MFA.lnk'),(Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Bliss MFA Portal.url'))) { if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file } }
    Remove-Item 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\BlissMFA' -Recurse -ErrorAction SilentlyContinue
    Write-Host ('Bliss MFA uninstalled. Private data and backups remain in '+$rootPath+'. Your subscription is unchanged. Restart Windows before testing sign-in.')
    Read-Host 'Press Enter to close'
} catch { Write-Host ('Uninstall could not finish: '+$_.Exception.Message); Read-Host 'Press Enter to close'; exit 1 }
