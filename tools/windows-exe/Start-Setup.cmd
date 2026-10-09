@echo off
rem Launched by Setup-BlissMFA-<version>.exe (IExpress) from its temporary extraction folder.
rem Re-launch as 64-bit: IExpress is 32-bit, and 32-bit PowerShell would write the
rem credential provider's registry settings to the WOW6432Node view.
if defined PROCESSOR_ARCHITEW6432 (
    "%SystemRoot%\Sysnative\cmd.exe" /c "%~f0"
    exit /b %errorlevel%
)
rem The IExpress exe has no elevation manifest: ask for administrator rights here, and wait,
rem because IExpress deletes this temporary folder as soon as this script returns.
net session >nul 2>&1
if errorlevel 1 (
    set "BLISS_SETUP_SCRIPT=%~f0"
    "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "try { $p = Start-Process -FilePath $env:ComSpec -ArgumentList ('/c \"' + $env:BLISS_SETUP_SCRIPT + '\"') -Verb RunAs -Wait -PassThru; exit $p.ExitCode } catch { Write-Host 'Bliss MFA setup needs administrator approval.'; exit 1 }"
    exit /b %errorlevel%
)
rem Keep the setup files in an administrator-only location, then run setup from there.
set "DEST=%ProgramFiles%\Bliss MFA\Setup\__VERSION__"
if not exist "%DEST%" mkdir "%DEST%"
for %%F in (BlissMFA-Appliance.zip Install-BlissEngine.ps1 Install-WindowsIntegration.ps1 Uninstall-BlissMFA.ps1 Update-BlissMFA.ps1 client-update.py Setup-BlissMFA.ps1 Setup-BlissMFA.cmd Enable-RdpProtection.ps1 Enable-RdpProtection.cmd README.txt) do (
    copy /y "%~dp0%%F" "%DEST%\%%F" >nul || (echo Could not copy %%F & pause & exit /b 1)
)
echo Bliss MFA __VERSION__ setup files: %DEST%
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%DEST%\Setup-BlissMFA.ps1"
set "RESULT=%errorlevel%"
if not "%RESULT%"=="0" (
    echo Setup did not complete ^(exit %RESULT%^). Record the message above.
    pause
)
exit /b %RESULT%
