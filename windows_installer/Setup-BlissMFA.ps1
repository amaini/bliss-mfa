[CmdletBinding()]
param(
    [ValidateSet('install','repair','update','check')][string]$Action='install',
    [string]$Root='C:\BlissMFA',
    [string]$UpdatesUrl='https://license.blissitek.ca',
    [switch]$ManualUpdates
)
$ErrorActionPreference='Stop'
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments='-NoProfile -ExecutionPolicy Bypass -File "'+$PSCommandPath+'" -Action '+$Action+' -Root "'+$Root+'" -UpdatesUrl "'+$UpdatesUrl+'"'
    if ($ManualUpdates) { $arguments+=' -ManualUpdates' }
    $p=Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList $arguments -Wait -PassThru
    exit $p.ExitCode
}
try {
    $controlRoot=$PSScriptRoot
    $build=Get-Content -LiteralPath (Join-Path $controlRoot 'installer.json') -Raw | ConvertFrom-Json
    $protected=Join-Path $env:ProgramFiles ('Bliss MFA Updater\'+$build.version)
    if ($Action -ne 'install' -and (Test-Path -LiteralPath $protected)) { $controlRoot=$protected }
    if ($Action -eq 'install') {
        $protected=Join-Path $env:ProgramFiles ('Bliss MFA Updater\'+$build.version)
        if (Test-Path -LiteralPath $protected) { throw 'Updater directory already exists; use its Repair shortcut.' }
        New-Item -ItemType Directory -Path $protected -Force | Out-Null
        & icacls.exe $protected /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Updater directory ACL failed.' }
        # Only fixed build components; no customer configuration is copied.
        foreach ($name in @('python','windows_installer','Setup-BlissMFA.ps1','installer.json','update-public.pem')) {
            Copy-Item -LiteralPath (Join-Path $controlRoot $name) -Destination (Join-Path $protected $name) -Recurse
        }
        $controlRoot=$protected
    }
    $python=Join-Path $controlRoot 'python\python.exe'
    $arguments=@((Join-Path $controlRoot 'windows_installer\manager.py'),$Action,'--root',$Root)
    if ($Action -eq 'install') {
        $arguments+=@('--archive',(Join-Path $PSScriptRoot 'BlissMFA-Appliance.zip'),'--sha256',$build.archive_sha256,'--updates-url',$UpdatesUrl,'--update-public-key',(Join-Path $controlRoot 'update-public.pem'))
        if (!$ManualUpdates) { $arguments+='--automatic' }
    }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw ('Installer action failed with exit '+$LASTEXITCODE+'. Preserve the message above for diagnosis.') }
    Write-Host ('Bliss MFA '+$Action+' completed.')
} catch {
    Write-Error $_
    exit 1
}
