$ErrorActionPreference='Stop'
if ($env:COMPUTERNAME -ne 'WIN-10VM-ASUS') { throw 'Wrong disposable VM.' }
$root='C:\BlissMFA'
$user=Get-LocalUser 'bliss_proto_test'
$users=Get-LocalGroup -SID 'S-1-5-32-545'
if (!(Get-LocalGroupMember $users | Where-Object SID -eq $user.SID)) {
    Add-LocalGroupMember -Group $users -Member $user
}
$file="$root\prototype-test-account.json"
$data=Get-Content $file -Raw | ConvertFrom-Json
$data | Add-Member -NotePropertyName windows_sid -NotePropertyValue $user.SID.Value -Force
$data | ConvertTo-Json | Set-Content -LiteralPath $file -Encoding UTF8
& "$root\python\python.exe" "$root\verify-vm-runtime.py"
if ($LASTEXITCODE -ne 0) { throw 'Client defaults / Windows password verification failed.' }
Disable-ScheduledTask -TaskName 'BlissMFA-PrototypeEngine' | Out-Null
try {
    $supervisor=@(Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -eq 'C:\BlissMFA\python\python.exe' -and
        $_.CommandLine -like '*C:\BlissMFA\bliss-mfa\scripts\run-engine.py*'
    })
    if ($supervisor.Count -ne 1) { throw 'Expected exactly one owned engine supervisor.' }
    & taskkill.exe /PID $supervisor[0].ProcessId /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop owned process tree.' }
    Stop-ScheduledTask -TaskName 'BlissMFA-PrototypeEngine'
    if (Get-NetTCPConnection -LocalPort 18090,18443 -State Listen -ErrorAction SilentlyContinue) {
        throw 'Engine listeners remained after stop.'
    }
    & "$root\python\python.exe" "$root\verify-vm-runtime.py" --outage
    if ($LASTEXITCODE -ne 0) { throw 'Engine outage was not denied.' }
} finally {
    Enable-ScheduledTask -TaskName 'BlissMFA-PrototypeEngine' | Out-Null
    Start-ScheduledTask -TaskName 'BlissMFA-PrototypeEngine'
}
Start-Sleep -Seconds 3
& "$root\python\python.exe" "$root\verify-vm-runtime.py"
if ($LASTEXITCODE -ne 0) { throw 'Restart recovery verification failed.' }
'PASS controlled engine outage and restart recovery'
