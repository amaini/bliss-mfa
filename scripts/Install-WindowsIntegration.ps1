[CmdletBinding()]
param([string]$Root='C:\BlissMFA')
$ErrorActionPreference='Stop'
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run as Administrator.' }
$rootPath=(Resolve-Path -LiteralPath $Root).Path
if (!(Test-Path -LiteralPath (Join-Path $rootPath 'bliss-mfa\.local\engine\appliance.json'))) { throw 'Installed appliance configuration missing.' }
$tools=Join-Path $env:ProgramFiles 'Bliss MFA'
New-Item -ItemType Directory -Path $tools -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Uninstall-BlissMFA.ps1') -Destination (Join-Path $tools 'Uninstall-BlissMFA.ps1') -Force
[ordered]@{Root=$rootPath;Version='0.1.1'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $tools 'installation.json')
$menu=Join-Path ([Environment]::GetFolderPath('CommonPrograms')) 'Bliss MFA'
New-Item -ItemType Directory -Path $menu -Force | Out-Null
$link="[InternetShortcut]`r`nURL=https://localhost:19443`r`n"
Set-Content -LiteralPath (Join-Path $menu 'Bliss MFA Portal.url') -Value $link -Encoding ASCII
Set-Content -LiteralPath (Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Bliss MFA Portal.url') -Value $link -Encoding ASCII
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut((Join-Path $menu 'Uninstall Bliss MFA.lnk'))
$shortcut.TargetPath=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shortcut.Arguments='-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $tools 'Uninstall-BlissMFA.ps1')+'"'
$shortcut.Save()
$key='HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\BlissMFA'
New-Item $key -Force | Out-Null
$values=@{DisplayName='Bliss MFA';DisplayVersion='0.1.1';Publisher='Bliss IT Solutions Inc.';InstallLocation=$rootPath;UninstallString=('"'+$shortcut.TargetPath+'" '+$shortcut.Arguments)}
foreach ($entry in $values.GetEnumerator()) { New-ItemProperty $key -Name $entry.Key -Value $entry.Value -PropertyType String -Force | Out-Null }
foreach ($name in @('NoModify','NoRepair')) { New-ItemProperty $key -Name $name -Value 1 -PropertyType DWord -Force | Out-Null }
Write-Output 'Desktop and Start menu shortcuts created; Bliss MFA registered in Installed apps.'
