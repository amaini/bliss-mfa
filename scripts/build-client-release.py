"""Create the customer download with a fixed-hash, elevated Windows setup entry."""
import argparse
import hashlib
import json
import os
import shutil
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--archive', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
with args.archive.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
setup = r'''$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments='-NoProfile -ExecutionPolicy Bypass -File "'+$PSCommandPath+'"'
    $process=Start-Process powershell.exe -ArgumentList $arguments -Verb RunAs -WindowStyle Normal -Wait -PassThru
    exit $process.ExitCode
}
try {
    & (Join-Path $PSScriptRoot 'Install-BlissEngine.ps1') -Archive (Join-Path $PSScriptRoot 'BlissMFA-Appliance.zip') -ExpectedSHA256 '__HASH__'
    Start-Process 'C:\BlissMFA\bliss-mfa\.local\engine\Open-Appliance.html'
} catch {
    Write-Host 'Setup could not finish. Keep this window open and record the error below.'
    Write-Error $_
    Read-Host 'Press Enter to close'
    exit 1
}
'''.replace('__HASH__', digest)
enable = r'''$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $process=Start-Process powershell.exe -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "'+$PSCommandPath+'"') -Verb RunAs -WindowStyle Normal -Wait -PassThru
    exit $process.ExitCode
}
try {
    $username=Read-Host 'Enter the existing local Windows account you enrolled in the portal'
    $confirmed=Read-Host 'Keep your recovery administrator session or console available. Type READY when tested'
    if ($confirmed -cne 'READY') { throw 'Recovery access must be available before enabling protection.' }
    & 'C:\BlissMFA\bliss-mfa\scripts\Enable-RdpProtection.ps1' -ProtectedUser $username -RecoveryConfirmed
} catch { Write-Error $_; Read-Host 'Press Enter to close'; exit 1 }
Read-Host 'Press Enter to close, then perform the RDP test in your portal checklist'
'''
guide = '''Bliss MFA Windows prototype

1. Complete your purchase in the Bliss client portal. Generate your activation code.
2. Extract this download into a local folder. Run Setup-BlissMFA.cmd and accept
   Windows elevation. Use a local administrator that you will retain for recovery.
   The installer verifies the appliance archive, installs its service and the signed
   upstream Windows provider, and opens the private local setup page.
3. Create your local portal owner. Activate your paid license on the License page.
4. On RDP Users, add an existing local Windows account, scan its authenticator QR
   code, and verify a fresh code. The prototype does not create Windows accounts.
5. Keep your tested recovery-administrator session or console available. Run
   Enable-RdpProtection.cmd from this extracted download. It checks the license and
   enrollment, verifies a fresh code through the installed native client, and enables
   RDP logon/unlock protection. The recovery administrator remains excluded.
6. Wait for the next code. Test RDP sign-in with the enrolled account and its Windows
   password; then check incorrect and empty OTP rejection. Record the result on the
   local portal's Get started page.

Local portal: https://localhost:19443 (on the installed Windows machine).
Reopen it using the Bliss MFA Portal shortcut on your desktop or Start menu.
Uninstall through Windows Settings > Apps > Installed apps > Bliss MFA, or the
Start menu's Uninstall Bliss MFA shortcut. Private data and backups are retained.
Uninstalling removes RDP MFA protection and does not cancel your subscription.
Private setup page: C:\\BlissMFA\\bliss-mfa\\.local\\engine\\Open-Appliance.html

The provider initially has enforcement disabled. Enabling protection affects RDP
accounts on this machine: enroll accounts that need RDP access before enabling it.
Console logon stays available for recovery. This prototype has been tested on the
disposable Windows 10 Pro x64 VM; validate other Windows editions before rollout.
The installer adds this machine's private localhost certificate to its trusted root
store so the local portal can use HTTPS. MFA seeds and the certificate key remain
inside the protected local installation directory.

Disable protection from an elevated recovery PowerShell:
  & 'C:\\BlissMFA\\bliss-mfa\\scripts\\Enable-RdpProtection.ps1' -Disable

For encrypted backup, stop BlissMFAEngine, run the included engine-backup.py with
--engine-stopped, and restart the service. Keep your backup passphrase separately.
Restore into a new directory; restoring never overwrites a live installation.
'''
args.output.parent.mkdir(parents=True, exist_ok=True)
# Reproducible wrapper: fixed entry timestamp (SOURCE_DATE_EPOCH convention) and mode.
ZIP_TIME = time.gmtime(int(os.environ.get('SOURCE_DATE_EPOCH', '315532800')))[:6]


def entry(name, compression=zipfile.ZIP_DEFLATED):
    info = zipfile.ZipInfo(name, ZIP_TIME)
    info.compress_type = compression
    info.external_attr = 0o644 << 16
    return info


with zipfile.ZipFile(args.output, 'w') as release:
    # Already compressed; avoid a second costly compression pass.
    with args.archive.open('rb') as source, release.open(entry('BlissMFA-Appliance.zip', zipfile.ZIP_STORED),
                                                         'w', force_zip64=True) as target:
        shutil.copyfileobj(source, target, 1 << 20)
    release.writestr(entry('Install-BlissEngine.ps1'), (REPO / 'scripts/Install-BlissEngine.ps1').read_bytes())
    for name in ('Install-WindowsIntegration.ps1', 'Uninstall-BlissMFA.ps1', 'Update-BlissMFA.ps1', 'client-update.py'):
        release.writestr(entry(name), (REPO / 'scripts' / name).read_bytes())
    release.writestr(entry('Setup-BlissMFA.ps1'), setup)
    release.writestr(entry('Enable-RdpProtection.ps1'), enable)
    release.writestr(entry('README.txt'), guide)
    for name in ('Setup-BlissMFA', 'Enable-RdpProtection'):
        release.writestr(entry(name + '.cmd'),
                         '@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0' + name + '.ps1"\r\n')
with args.output.open('rb') as stream:
    release_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
metadata = {'filename': args.output.name, 'sha256': release_digest,
            'appliance_sha256': digest, 'size': args.output.stat().st_size, 'prototype': True}
args.output.with_suffix('.json').write_text(json.dumps(metadata, indent=2))
print(json.dumps(metadata, indent=2))
