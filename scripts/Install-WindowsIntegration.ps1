[CmdletBinding()]
param([string]$Root='C:\BlissMFA', [ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version='0.1.1')
$ErrorActionPreference='Stop'
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run as Administrator.' }
$rootPath=(Resolve-Path -LiteralPath $Root).Path
if (!(Test-Path -LiteralPath (Join-Path $rootPath 'bliss-mfa\.local\engine\appliance.json'))) { throw 'Installed appliance configuration missing.' }
$tools=Join-Path $env:ProgramFiles 'Bliss MFA'
New-Item -ItemType Directory -Path $tools -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Uninstall-BlissMFA.ps1') -Destination (Join-Path $tools 'Uninstall-BlissMFA.ps1') -Force
$existing=Join-Path $tools 'installation.json'
$releaseVersion=Join-Path $rootPath 'bliss-mfa\deployment\release-version.json'
# deploymentelease-version.json is authoritative; signed updates replace it. A leftover record
# from an earlier installation is used only for releases that predate the version file.
if (Test-Path -LiteralPath $releaseVersion) { $Version=(Get-Content $releaseVersion -Raw | ConvertFrom-Json).version }
elseif (Test-Path -LiteralPath $existing) { $Version=(Get-Content $existing -Raw | ConvertFrom-Json).Version }
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid installed application version.' }
[ordered]@{Root=$rootPath;Version=$Version} | ConvertTo-Json | Set-Content -LiteralPath $existing
$menu=Join-Path ([Environment]::GetFolderPath('CommonPrograms')) 'Bliss MFA'
New-Item -ItemType Directory -Path $menu -Force | Out-Null
$link="[InternetShortcut]`r`nURL=https://localhost:19443`r`n"
Set-Content -LiteralPath (Join-Path $menu 'Bliss MFA Portal.url') -Value $link -Encoding ASCII
Set-Content -LiteralPath (Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Bliss MFA Portal.url') -Value $link -Encoding ASCII
$shell=New-Object -ComObject WScript.Shell
$updateKey=Join-Path $rootPath 'bliss-mfa\deployment\update-public.pem'
if (Test-Path -LiteralPath $updateKey) {
    foreach($name in @('Update-BlissMFA.ps1','client-update.py')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $tools $name) -Force
    }
    $pinnedKey=Join-Path $tools 'update-public.pem'
    if (Test-Path -LiteralPath $pinnedKey) {
        if ((Get-FileHash $pinnedKey).Hash -ne (Get-FileHash $updateKey).Hash) { throw 'Update trust key changed; explicit key migration required.' }
    } else { Copy-Item -LiteralPath $updateKey -Destination $pinnedKey }
    $update=$shell.CreateShortcut((Join-Path $menu 'Check for Bliss MFA updates.lnk'))
    $update.TargetPath=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $update.Arguments='-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $tools 'Update-BlissMFA.ps1')+'"'
    $update.Save()
}
$shortcut=$shell.CreateShortcut((Join-Path $menu 'Uninstall Bliss MFA.lnk'))
$shortcut.TargetPath=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shortcut.Arguments='-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $tools 'Uninstall-BlissMFA.ps1')+'"'
$shortcut.Save()
$key='HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\BlissMFA'
New-Item $key -Force | Out-Null
$values=@{DisplayName='Bliss MFA';DisplayVersion=$Version;Publisher='Bliss IT Solutions Inc.';InstallLocation=$rootPath;UninstallString=('"'+$shortcut.TargetPath+'" '+$shortcut.Arguments)}
foreach ($entry in $values.GetEnumerator()) { New-ItemProperty $key -Name $entry.Key -Value $entry.Value -PropertyType String -Force | Out-Null }
foreach ($name in @('NoModify','NoRepair')) { New-ItemProperty $key -Name $name -Value 1 -PropertyType DWord -Force | Out-Null }
Write-Output 'Desktop and Start menu shortcuts created; Bliss MFA registered in Installed apps.'
