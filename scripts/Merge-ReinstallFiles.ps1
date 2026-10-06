# Reinstall over retained data: replace application binaries from a verified staging
# extraction inside Root. Private data (bliss-mfa\.local), backups and updates are never touched.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Root,
    [Parameter(Mandatory)][string]$Staging
)
$ErrorActionPreference='Stop'
$rootPath=(Resolve-Path -LiteralPath $Root).Path.TrimEnd('\')
$stagingPath=(Resolve-Path -LiteralPath $Staging).Path.TrimEnd('\')
if (!$stagingPath.StartsWith($rootPath+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Staging must be inside the installation directory.' }
if (Test-Path -LiteralPath (Join-Path $stagingPath 'bliss-mfa\.local')) { throw 'Release archive must not contain private data.' }

function Resolve-Owned([string]$relative) {
    $target=[IO.Path]::GetFullPath((Join-Path $rootPath $relative))
    if (!$target.StartsWith($rootPath+'\',[StringComparison]::OrdinalIgnoreCase) -or
        $target.StartsWith((Join-Path $rootPath 'bliss-mfa\.local'),[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Unsafe reinstall path.'
    }
    return $target
}

# Application content shipped by every release. Removed first so stale files cannot linger.
$binaries=@('python','node','portal','php-runtime','multiotp-engine','installers','manifest.json',
            'bliss-mfa\apps','bliss-mfa\services','bliss-mfa\scripts','bliss-mfa\deployment','bliss-mfa\website')
$targets=foreach ($relative in $binaries) { Resolve-Owned $relative }
foreach ($target in $targets) {
    if ((Test-Path -LiteralPath $target) -and ((Get-Item -LiteralPath $target -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Refusing to replace a linked application directory.'
    }
}
foreach ($target in $targets) {
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
}

foreach ($item in Get-ChildItem -LiteralPath $stagingPath -Force) {
    $children=if ($item.Name -eq 'bliss-mfa') { Get-ChildItem -LiteralPath $item.FullName -Force } else { @($item) }
    $prefix=if ($item.Name -eq 'bliss-mfa') { 'bliss-mfa\' } else { '' }
    if ($prefix) { New-Item -ItemType Directory -Path (Join-Path $rootPath 'bliss-mfa') -Force | Out-Null }
    foreach ($child in $children) {
        $destination=Resolve-Owned ($prefix+$child.Name)
        if (Test-Path -LiteralPath $destination) { throw ('Refusing to replace unrecognised path: '+$prefix+$child.Name) }
        Move-Item -LiteralPath $child.FullName -Destination $destination
    }
}
Remove-Item -LiteralPath $stagingPath -Recurse -Force
Write-Output 'Application binaries replaced; retained private data preserved.'
