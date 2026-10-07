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
    # Include bootstrap identity so a corrected setup can recover an older attempt.
    $bootstrapHash=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.Substring(0,16)
    $protected=Join-Path $env:ProgramFiles ('Bliss MFA Updater\'+$build.version+'-'+$bootstrapHash)
    if ($Action -eq 'install') {
        $parent=Split-Path -Parent $protected
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        if ((Get-Item -LiteralPath $parent).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Updater parent cannot be a reparse point.' }
        & icacls.exe $parent /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Updater directory ACL failed.' }
        $components=@('python','windows_installer','Setup-BlissMFA.ps1','installer.json','update-public.pem')
        if (Test-Path -LiteralPath $protected) {
            if ((Get-Item -LiteralPath $protected).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Updater directory cannot be a reparse point.' }
            if (Get-ChildItem -LiteralPath $protected -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { throw 'Updater contents cannot contain reparse points.' }
            # Never execute an existing controller merely because its directory exists.
            foreach ($name in $components) {
                $source=Join-Path $controlRoot $name
                $files=if (Test-Path -LiteralPath $source -PathType Container) { Get-ChildItem -LiteralPath $source -File -Recurse } else { Get-Item -LiteralPath $source }
                foreach ($file in $files) {
                    $relative=$file.FullName.Substring($controlRoot.Length).TrimStart('\')
                    $target=Join-Path $protected $relative
                    if (!(Test-Path -LiteralPath $target -PathType Leaf) -or (Get-FileHash -LiteralPath $target).Hash -ne (Get-FileHash -LiteralPath $file.FullName).Hash) {
                        throw ('Existing updater verification failed: '+$relative+'. Preserve it for diagnosis; do not delete installed state.')
                    }
                }
            }
        } else {
            $stage=Join-Path $parent ('staging-'+[guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $stage | Out-Null
            # Only fixed build components; no customer configuration is copied.
            foreach ($name in $components) {
                Copy-Item -LiteralPath (Join-Path $controlRoot $name) -Destination (Join-Path $stage $name) -Recurse
            }
            Move-Item -LiteralPath $stage -Destination $protected
        }
        $controlRoot=$protected
        $receipt=Join-Path $Root 'bliss-mfa\.local\updater\installation.json'
        if (Test-Path -LiteralPath $receipt -PathType Leaf) {
            $Action='repair'
            Write-Host 'Managed installation found; retrying with repair and preserving private configuration.'
        } elseif (Test-Path -LiteralPath $Root) {
            throw 'Installation directory exists without a managed receipt. Preserve it; prototype migration or failed-install diagnosis is required.'
        }
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
    # Write-Error would itself terminate under Stop before our explicit exit.
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
