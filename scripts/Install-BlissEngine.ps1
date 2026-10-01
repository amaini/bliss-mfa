# Reusable clean Windows engine installation. Run elevated.
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
$rootPath=[IO.Path]::GetFullPath($Root)
if (Test-Path -LiteralPath $rootPath) { throw 'Installation directory exists; use the upgrade workflow.' }
if ((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash -ne $ExpectedSHA256) { throw 'Release archive hash mismatch.' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip=[IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $Archive))
try {
    $names=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $zip.Entries) {
        $name=$entry.FullName.Replace('/','\')
        $target=[IO.Path]::GetFullPath((Join-Path $rootPath $name))
        if (!$target.StartsWith($rootPath.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase) -or
            $name.Contains(':') -or !$names.Add($name)) { throw 'Unsafe or duplicate release archive path.' }
    }
} finally { $zip.Dispose() }
New-Item -ItemType Directory -Path $rootPath | Out-Null
& icacls.exe $rootPath /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Private installation ACL failed.' }
Expand-Archive -LiteralPath $Archive -DestinationPath $rootPath
$manifest=Get-Content (Join-Path $rootPath 'manifest.json') -Raw | ConvertFrom-Json
foreach ($entry in $manifest.PSObject.Properties) {
    $target=[IO.Path]::GetFullPath((Join-Path $rootPath $entry.Name))
    if (!$target.StartsWith($rootPath.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe manifest path.' }
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $entry.Value) { throw 'Release file integrity failed.' }
}
$runtime=Join-Path $rootPath 'installers\vc_redist.x64.exe'
if ((Get-AuthenticodeSignature $runtime).Status -ne 'Valid') { throw 'Runtime publisher signature invalid.' }
$vc=Start-Process -FilePath $runtime -ArgumentList '/install /quiet /norestart' -WindowStyle Hidden -Wait -PassThru
if ($vc.ExitCode -notin @(0,1638,3010)) { throw 'VC runtime installation failed.' }
$python=Join-Path $rootPath 'python\python.exe'
$launcher=Join-Path $rootPath 'bliss-mfa\scripts\run-engine.py'
& $python $launcher --initialize
if ($LASTEXITCODE -ne 0) { throw 'Engine configuration initialization failed.' }
if (!$EngineOnly) {
    & $python $launcher --initialize-appliance --license-url $LicenseServerUrl --public-key (Join-Path $rootPath 'bliss-mfa\deployment\license-public.pem')
    if ($LASTEXITCODE -ne 0) { throw 'Appliance configuration initialization failed.' }
}
& (Join-Path $rootPath 'bliss-mfa\scripts\Install-EngineService.ps1') -Root $rootPath -Wrapper (Join-Path $rootPath 'installers\WinSW-x64.exe')
if (!$EngineOnly) {
    & (Join-Path $rootPath 'bliss-mfa\scripts\Stage-BlissProvider.ps1') -Root $rootPath
    $certificate=Join-Path $rootPath 'bliss-mfa\.local\engine\engine-cert.pem'
    Import-Certificate -FilePath $certificate -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
    $welcome=Join-Path $rootPath 'bliss-mfa\.local\engine\Open-Appliance.html'
    & icacls.exe $welcome /grant ('*'+$identity.User.Value+':R') | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Setup-page access failed.' }
    & (Join-Path $PSScriptRoot 'Install-WindowsIntegration.ps1') -Root $rootPath
    Write-Output ('Appliance installed. Open the private setup page: '+$welcome)
} else {
    Write-Output 'Engine installed. Complete appliance setup and enroll a recovery-tested user before enabling RDP enforcement.'
}
