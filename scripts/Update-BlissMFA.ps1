[CmdletBinding()]
param([switch]$Rollback)
$ErrorActionPreference='Stop'
$tools=Join-Path $env:ProgramFiles 'Bliss MFA'
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments='-NoProfile -ExecutionPolicy Bypass -File "'+$PSCommandPath+'"'
    if ($Rollback) { $arguments+=' -Rollback' }
    $process=Start-Process powershell.exe -ArgumentList $arguments -Verb RunAs -Wait -PassThru
    exit $process.ExitCode
}
try {
    $installation=Join-Path $tools 'installation.json'
    $installed=Get-Content -LiteralPath $installation -Raw | ConvertFrom-Json
    $arguments=@((Join-Path $tools 'client-update.py'),'--installation',$installation,'--key',(Join-Path $tools 'update-public.pem'))
    if ($Rollback) { $arguments+='--rollback' }
    & (Join-Path $installed.Root 'python\python.exe') @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Update failed. Record the message above; your recovery administrator remains available.' }
} catch { Write-Host $_; Read-Host 'Press Enter to close'; exit 1 }
Read-Host 'Press Enter to close'
