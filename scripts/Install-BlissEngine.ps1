# Windows engine installation: clean install, or reinstall over retained private data. Run elevated.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Archive,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ExpectedSHA256,
    [string]$Root='C:\BlissMFA',
    [string]$LicenseServerUrl='https://license.blissitek.ca',
    [switch]$EngineOnly
)
$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run this installer as Administrator.' }
$rootPath=[IO.Path]::GetFullPath($Root).TrimEnd('\')
if (Get-Service 'BlissMFAEngine' -ErrorAction SilentlyContinue) { throw 'Bliss MFA is installed; use the update shortcut, or uninstall before reinstalling.' }
if (!$EngineOnly -and (Test-Path 'Registry::HKEY_CLASSES_ROOT\CLSID\{FCEFDFAB-B0A1-4C4D-8B2B-4FF4E0A3D978}')) {
    throw 'A credential provider is already installed; uninstall Bliss MFA before reinstalling.'
}
$privateEngine=Join-Path $rootPath 'bliss-mfa\.local\engine'
$reinstall=$false
if (Test-Path -LiteralPath $rootPath) {
    if (Test-Path -LiteralPath (Join-Path $privateEngine 'config.json')) { $reinstall=$true }
    elseif (@(Get-ChildItem -LiteralPath $rootPath -Force).Count -gt 0) {
        throw 'Installation directory exists without retained Bliss MFA data; choose an empty location.'
    }
}
if ((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash -ne $ExpectedSHA256) { throw 'Release archive hash mismatch.' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip=[IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $Archive))
try {
    $names=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $zip.Entries) {
        $name=$entry.FullName.Replace('/','\')
        $target=[IO.Path]::GetFullPath((Join-Path $rootPath $name))
        if (!$target.StartsWith($rootPath+'\',[StringComparison]::OrdinalIgnoreCase) -or
            $name.Contains(':') -or !$names.Add($name)) { throw 'Unsafe or duplicate release archive path.' }
        if ($name -match '^(bliss-mfa\\\.local|updates|reinstall-staging)(\\|$)') {
            throw 'Release archive must not contain private or working paths.'
        }
    }
} finally { $zip.Dispose() }

function Test-Manifest([string]$base) {
    $manifest=Get-Content (Join-Path $base 'manifest.json') -Raw | ConvertFrom-Json
    foreach ($entry in $manifest.PSObject.Properties) {
        $target=[IO.Path]::GetFullPath((Join-Path $base $entry.Name))
        if (!$target.StartsWith($base.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe manifest path.' }
        if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $entry.Value) { throw 'Release file integrity failed.' }
    }
}

if ($reinstall) {
    # Verify the release and the retained identity before any existing file is changed.
    $staging=Join-Path $rootPath 'reinstall-staging'
    if (Test-Path -LiteralPath $staging) {
        if ((Get-Item -LiteralPath $staging -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing a linked staging directory.' }
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
    Expand-Archive -LiteralPath $Archive -DestinationPath $staging
    Test-Manifest $staging
    $inspection=@((Join-Path $staging 'bliss-mfa\scripts\run-engine.py'),'--config',(Join-Path $privateEngine 'config.json'),'--inspect-retained')
    if ($EngineOnly) { $inspection+='--engine-only' }
    $retained=& (Join-Path $staging 'python\python.exe') @inspection
    $inspectionExit=$LASTEXITCODE
    if ($inspectionExit -ne 0) {
        Remove-Item -LiteralPath $staging -Recurse -Force
        if ($inspectionExit -eq 3) { throw 'Retained appliance identity is lost. Nothing was changed. See docs/reinstall-and-identity-recovery.md.' }
        throw 'Retained Bliss MFA data is incomplete. Nothing was changed. See docs/reinstall-and-identity-recovery.md.'
    }
    Write-Output ('Reinstalling over retained data: '+$retained)
    & (Join-Path $staging 'bliss-mfa\scripts\Merge-ReinstallFiles.ps1') -Root $rootPath -Staging $staging
} else {
    New-Item -ItemType Directory -Path $rootPath -Force | Out-Null
    & icacls.exe $rootPath /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Private installation ACL failed.' }
    Expand-Archive -LiteralPath $Archive -DestinationPath $rootPath
}
Test-Manifest $rootPath

$runtime=Join-Path $rootPath 'installers\vc_redist.x64.exe'
if ((Get-AuthenticodeSignature $runtime).Status -ne 'Valid') { throw 'Runtime publisher signature invalid.' }
$vc=Start-Process -FilePath $runtime -ArgumentList '/install /quiet /norestart' -WindowStyle Hidden -Wait -PassThru
if ($vc.ExitCode -notin @(0,1638,3010)) { throw 'VC runtime installation failed.' }
$python=Join-Path $rootPath 'python\python.exe'
$launcher=Join-Path $rootPath 'bliss-mfa\scripts\run-engine.py'
# Retained configuration holds the engine secrets, certificate and appliance identity: never regenerate it.
if (!(Test-Path -LiteralPath (Join-Path $privateEngine 'config.json'))) {
    & $python $launcher --initialize
    if ($LASTEXITCODE -ne 0) { throw 'Engine configuration initialization failed.' }
}
if (!$EngineOnly -and !(Test-Path -LiteralPath (Join-Path $privateEngine 'appliance.json'))) {
    & $python $launcher --initialize-appliance --license-url $LicenseServerUrl --public-key (Join-Path $rootPath 'bliss-mfa\deployment\license-public.pem')
    if ($LASTEXITCODE -ne 0) { throw 'Appliance configuration initialization failed.' }
}
& (Join-Path $rootPath 'bliss-mfa\scripts\Install-EngineService.ps1') -Root $rootPath -Wrapper (Join-Path $rootPath 'installers\WinSW-x64.exe')
if (!$EngineOnly) {
    & (Join-Path $rootPath 'bliss-mfa\scripts\Stage-BlissProvider.ps1') -Root $rootPath
    $certificate=Join-Path $privateEngine 'engine-cert.pem'
    Import-Certificate -FilePath $certificate -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
    $welcome=Join-Path $privateEngine 'Open-Appliance.html'
    & icacls.exe $welcome /grant ('*'+$identity.User.Value+':R') | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Setup-page access failed.' }
    & (Join-Path $PSScriptRoot 'Install-WindowsIntegration.ps1') -Root $rootPath
    if ($reinstall) {
        Write-Output 'Appliance reinstalled with its retained identity, license, users and enrollment. RDP protection starts disabled: run Enable-RdpProtection after testing a fresh code.'
    } else {
        Write-Output ('Appliance installed. Open the private setup page: '+$welcome)
    }
} else {
    Write-Output 'Engine installed. Complete appliance setup and enroll a recovery-tested user before enabling RDP enforcement.'
}
