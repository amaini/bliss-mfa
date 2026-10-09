# Wrap a verified Bliss MFA customer ZIP into one self-extracting Setup-BlissMFA-<version>.exe (IExpress).
# The exe extracts to a temporary folder and runs Start-Setup.cmd, which copies the files to
# %ProgramFiles%\Bliss MFA\Setup\<version> and runs Setup-BlissMFA.ps1 from there.
param(
    [Parameter(Mandatory)][string]$Zip,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedSHA256,
    [Parameter(Mandatory)][ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version,
    [Parameter(Mandatory)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
if ((Get-FileHash -LiteralPath $Zip).Hash -ne $ExpectedSHA256.ToUpper()) { throw 'Installer ZIP hash mismatch.' }
$work = Join-Path $env:TEMP ("bliss-exe-" + [guid]::NewGuid().ToString('N'))
$stage = Join-Path $work 'stage'
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Expand-Archive -LiteralPath $Zip -DestinationPath $stage
$launcher = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Start-Setup.cmd') -Raw).Replace('__VERSION__', $Version)
[IO.File]::WriteAllText((Join-Path $stage 'Start-Setup.cmd'), $launcher, [Text.Encoding]::ASCII)
$files = @(Get-ChildItem -LiteralPath $stage -File | ForEach-Object Name)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$target = Join-Path (Resolve-Path $OutputDirectory) "Setup-BlissMFA-$Version.exe"
if (Test-Path -LiteralPath $target) { throw "Output exists: $target" }
$strings = @("InstallPrompt=", "DisplayLicense=", "FinishMessage=", "TargetName=$target",
    "FriendlyName=Bliss MFA $Version Setup", "AppLaunched=cmd.exe /c Start-Setup.cmd", "PostInstallCmd=<None>",
    "AdminQuietInstCmd=cmd.exe /c Start-Setup.cmd", "UserQuietInstCmd=cmd.exe /c Start-Setup.cmd")
for ($i = 0; $i -lt $files.Count; $i++) { $strings += "FILE$i=`"$($files[$i])`"" }
$sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=0
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=%PostInstallCmd%
AdminQuietInstCmd=%AdminQuietInstCmd%
UserQuietInstCmd=%UserQuietInstCmd%
SourceFiles=SourceFiles
[Strings]
$($strings -join "`r`n")
[SourceFiles]
SourceFiles0=$stage\
[SourceFiles0]
$((0..($files.Count - 1) | ForEach-Object { "%FILE$_%=" }) -join "`r`n")
"@
$sedPath = Join-Path $work 'bliss.sed'
[IO.File]::WriteAllText($sedPath, $sed, [Text.Encoding]::ASCII)
$p = Start-Process -FilePath "$env:SystemRoot\System32\iexpress.exe" -ArgumentList @('/N', '/Q', $sedPath) -Wait -PassThru
if (!(Test-Path -LiteralPath $target)) { throw "IExpress did not produce the exe (exit $($p.ExitCode))." }
Remove-Item -LiteralPath $work -Recurse -Force
$hash = (Get-FileHash -LiteralPath $target).Hash.ToLower()
Set-Content -LiteralPath "$target.sha256" -Value "$hash  $(Split-Path $target -Leaf)" -Encoding ascii
[pscustomobject]@{ Exe = $target; Size = (Get-Item $target).Length; SHA256 = $hash; Files = $files.Count }
