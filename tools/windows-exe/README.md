# Single-file Windows setup (`Setup-BlissMFA-<version>.exe`)

Wraps a verified customer ZIP (`bliss-mfa-windows-<version>.zip` from `scripts/build-release.py`) into one
self-extracting exe built with Windows' own IExpress (nothing is installed).

```powershell
& tools\windows-exe\Build-BlissExe.ps1 -Zip <release>\bliss-mfa-windows-0.1.11.zip -ExpectedSHA256 <installer sha256 from release.json> -Version 0.1.11 -OutputDirectory <folder>
```

The exe extracts to a temporary folder and runs `Start-Setup.cmd`, which:
- relaunches itself as 64-bit (IExpress is 32-bit; 32-bit PowerShell would write the credential
  provider's settings to the WOW6432Node registry view);
- asks for administrator rights itself (the IExpress exe has no elevation manifest) and waits, because
  IExpress deletes its temporary folder when the launcher returns;
- copies the setup files to `%ProgramFiles%\Bliss MFA\Setup\<version>` (administrator-only) and runs
  `Setup-BlissMFA.ps1` from there, keeping `Enable-RdpProtection.cmd` and `README.txt` available.

`/Q` (silent) runs the same launcher. When testing over SSH, keep the session open
(`Start-Process ... -Wait`): Windows ends processes started by a closed SSH session.

The exe is not Authenticode-signed; SmartScreen warns until a code-signing certificate is used.
