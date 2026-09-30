# First engine deployment on the disposable VM. Run through encrypted remoting.
[CmdletBinding()]
param(
    [string]$Archive = 'C:\Users\Abhishek\Downloads\BlissMFA-engine-deployment.zip',
    [string]$ExpectedComputerName = 'WIN-10VM-ASUS',
    [string]$ExpectedTailscaleAddress = '100.83.112.5'
)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne $ExpectedComputerName) { throw 'Target identity mismatch.' }
if (!(Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -eq $ExpectedTailscaleAddress)) {
    throw 'Target Tailscale address mismatch.'
}
$root = 'C:\BlissMFA'
if (Test-Path $root) { throw 'Deployment root exists; use the documented upgrade procedure.' }
New-Item -ItemType Directory -Path $root | Out-Null
& icacls.exe $root /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not restrict deployment ACL.' }
Expand-Archive -LiteralPath $Archive -DestinationPath $root
$manifest = Get-Content "$root\manifest.json" -Raw | ConvertFrom-Json
foreach ($entry in $manifest.PSObject.Properties) {
    $file = Join-Path $root $entry.Name
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.Value) {
        throw "Package integrity failed: $($entry.Name)"
    }
}
$runtime = "$root\installers\vc_redist.x64.exe"
if ((Get-AuthenticodeSignature $runtime).Status -ne 'Valid') { throw 'Runtime signature invalid.' }
$vc = Start-Process -FilePath $runtime -ArgumentList '/install /quiet /norestart' -Wait -PassThru -WindowStyle Hidden
if ($vc.ExitCode -notin @(0, 1638, 3010)) { throw "Runtime install failed: $($vc.ExitCode)" }
$python = "$root\python\python.exe"
$launcher = "$root\bliss-mfa\scripts\run-engine.py"
& $python $launcher --initialize
if ($LASTEXITCODE -ne 0) { throw 'Engine initialization failed.' }
& $python $launcher --check
if ($LASTEXITCODE -ne 0) { throw 'Engine startup verification failed.' }
$action = New-ScheduledTaskAction -Execute $python -Argument ('"' + $launcher + '"') -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'BlissMFA-PrototypeEngine' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Disposable VM engine prototype; loopback management and native TLS authentication.' | Out-Null
Start-ScheduledTask -TaskName 'BlissMFA-PrototypeEngine'
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:18090/health' -TimeoutSec 2
        if ($health.status -eq 'ok') { break }
    } catch { Start-Sleep -Seconds 1 }
}
if ($health.status -ne 'ok') { throw 'Installed task did not become ready.' }
[ordered]@{Computer=$env:COMPUTERNAME;Root=$root;RuntimeExit=$vc.ExitCode;Health=$health.status;Task=(Get-ScheduledTask 'BlissMFA-PrototypeEngine').State.ToString()} | ConvertTo-Json
