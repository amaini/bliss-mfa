# Install or migrate the engine to Windows Service Control Manager supervision.
[CmdletBinding()]
param(
    [string]$Root = 'C:\BlissMFA',
    [Parameter(Mandatory)][string]$Wrapper,
    [switch]$MigratePrototypeTask
)
$ErrorActionPreference = 'Stop'
$rootPath = (Resolve-Path -LiteralPath $Root).Path
$expectedHash = '05B82D46AD331CC16BDC00DE5C6332C1EF818DF8CEEFCD49C726553209B3A0DA'
if ((Get-FileHash -LiteralPath $Wrapper -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Wrapper does not match pinned official WinSW v2.12.0 x64 release.'
}
if (Get-Service 'BlissMFAEngine' -ErrorAction SilentlyContinue) { throw 'Engine service already installed.' }
$task = Get-ScheduledTask 'BlissMFA-PrototypeEngine' -ErrorAction SilentlyContinue
if ($task -and !$MigratePrototypeTask) { throw 'Explicit prototype migration required.' }
$python = Join-Path $rootPath 'python\python.exe'
$launcher = Join-Path $rootPath 'bliss-mfa\scripts\run-engine.py'
$config = Join-Path $rootPath 'bliss-mfa\.local\engine\config.json'
foreach ($file in @($python, $launcher, $config)) {
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw 'Engine runtime/configuration missing.' }
}
$serviceDir = Join-Path $rootPath 'service'
New-Item -ItemType Directory -Path $serviceDir -Force | Out-Null
& icacls.exe $serviceDir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Service ACL failed.' }
$serviceExe = Join-Path $serviceDir 'BlissMFAEngine.exe'
Copy-Item -LiteralPath $Wrapper -Destination $serviceExe
$xml = New-Object System.Xml.XmlDocument
$xml.LoadXml('<service/>')
$values = [ordered]@{
    id='BlissMFAEngine'; name='Bliss MFA Engine'; description='Local Bliss MFA authentication engine';
    executable=$python; startarguments=('"' + $launcher + '" --config "' + $config + '"');
    stopexecutable=$python; stoparguments=('"' + $launcher + '" --config "' + $config + '" --stop');
    workingdirectory=$rootPath; startmode='Automatic'; stoptimeout='30 sec'; hidewindow='true';
    logpath=(Join-Path $serviceDir 'logs')
}
foreach ($entry in $values.GetEnumerator()) {
    $node=$xml.CreateElement($entry.Key); $node.InnerText=$entry.Value; $xml.DocumentElement.AppendChild($node) | Out-Null
}
$failure=$xml.CreateElement('onfailure'); $failure.SetAttribute('action','restart'); $failure.SetAttribute('delay','10 sec'); $xml.DocumentElement.AppendChild($failure) | Out-Null
$log=$xml.CreateElement('log'); $log.SetAttribute('mode','roll'); $xml.DocumentElement.AppendChild($log) | Out-Null
$xml.Save((Join-Path $serviceDir 'BlissMFAEngine.xml'))
$installed=$false
try {
    if ($task) {
        Disable-ScheduledTask 'BlissMFA-PrototypeEngine' | Out-Null
        $owned = @(Get-CimInstance Win32_Process | Where-Object {
            $_.ExecutablePath -eq $python -and $_.CommandLine -like ('*' + $launcher + '*')
        })
        foreach ($process in $owned) {
            & taskkill.exe /PID $process.ProcessId /T /F | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Could not stop prototype process tree.' }
        }
        Stop-ScheduledTask 'BlissMFA-PrototypeEngine'
    }
    & $python $launcher --config $config --check
    if ($LASTEXITCODE -ne 0) { throw 'New runtime readiness failed.' }
    & $serviceExe install
    if ($LASTEXITCODE -ne 0) { throw 'Service installation failed.' }
    $installed=$true
    & $serviceExe start
    if ($LASTEXITCODE -ne 0) { throw 'Service start failed.' }
    $ready=$false
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        try { if ((Invoke-RestMethod 'http://127.0.0.1:18090/health' -TimeoutSec 2).status -eq 'ok') { $ready=$true; break } } catch {}
        Start-Sleep -Seconds 1
    }
    if (!$ready) { throw 'Service readiness timed out.' }
    [ordered]@{Service='BlissMFAEngine'; Status=(Get-Service 'BlissMFAEngine').Status.ToString(); PrototypeTaskDisabled=[bool]$task} | ConvertTo-Json
} catch {
    if ($installed) { & $serviceExe stop; & $serviceExe uninstall }
    if ($task) { Enable-ScheduledTask 'BlissMFA-PrototypeEngine' | Out-Null; Start-ScheduledTask 'BlissMFA-PrototypeEngine' }
    throw
}
