[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Protect','Install','Repair','Stop','Start','Ready','Integration')][string]$Action,
    [Parameter(Mandatory)][string]$Root,
    [string]$ControlRoot,
    [switch]$AutomaticUpdates
)
$ErrorActionPreference='Stop'
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administrator access required.' }
$rootPath=[IO.Path]::GetFullPath($Root).TrimEnd('\')
if ($rootPath -eq [IO.Path]::GetPathRoot($rootPath).TrimEnd('\')) { throw 'Filesystem-root installation refused.' }
$python=Join-Path $rootPath 'python\python.exe'
$launcher=Join-Path $rootPath 'bliss-mfa\scripts\run-engine.py'
$serviceExe=Join-Path $rootPath 'service\BlissMFAEngine.exe'
function Assert-OwnedService {
    $service=Get-CimInstance Win32_Service -Filter "Name='BlissMFAEngine'"
    if ($service -and $service.PathName.Trim('"') -ne $serviceExe) { throw 'An engine service from another installation exists.' }
    return $service
}
function Run-Checked([string]$File,[string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('Operation failed: '+[IO.Path]::GetFileName($File)) }
}
function Initialize-Appliance {
    $private=Join-Path $rootPath 'bliss-mfa\.local\engine'
    if (!(Test-Path (Join-Path $private 'config.json'))) { Run-Checked $python @($launcher,'--initialize') }
    if (!(Test-Path (Join-Path $private 'appliance.json'))) {
        $receipt=Get-Content (Join-Path $rootPath 'bliss-mfa\.local\updater\installation.json') -Raw | ConvertFrom-Json
        Run-Checked $python @($launcher,'--initialize-appliance','--license-url',$receipt.updates_url,'--public-key',(Join-Path $rootPath 'bliss-mfa\deployment\license-public.pem'))
    }
}
switch ($Action) {
    Protect {
        & icacls.exe $rootPath /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Private installation ACL failed.' }
    }
    Stop {
        $owned=Assert-OwnedService
        if ($owned -and $owned.State -ne 'Stopped') {
            Run-Checked $serviceExe @('stop')
            (Get-Service BlissMFAEngine).WaitForStatus('Stopped',[TimeSpan]::FromSeconds(60))
        }
        $children=@(Get-CimInstance Win32_Process | Where-Object {
            $_.ExecutablePath -and $_.ExecutablePath.StartsWith($rootPath+'\',[StringComparison]::OrdinalIgnoreCase)
        })
        if ($children.Count) { throw 'An installed runtime process is still running; refusing file replacement.' }
    }
    Start {
        if (!(Assert-OwnedService)) { throw 'Engine service missing; use Repair.' }
        Run-Checked $serviceExe @('start')
        (Get-Service BlissMFAEngine).WaitForStatus('Running',[TimeSpan]::FromSeconds(60))
    }
    Install {
        if (Assert-OwnedService) { throw 'Existing service requires Repair.' }
        $runtime=Join-Path $rootPath 'installers\vc_redist.x64.exe'
        if ((Get-AuthenticodeSignature $runtime).Status -ne 'Valid') { throw 'Runtime publisher signature invalid.' }
        $vc=Start-Process $runtime -ArgumentList '/install /quiet /norestart' -WindowStyle Hidden -Wait -PassThru
        if ($vc.ExitCode -notin @(0,1638,3010)) { throw 'VC runtime installation failed.' }
        Initialize-Appliance
        & (Join-Path $rootPath 'bliss-mfa\scripts\Install-EngineService.ps1') -Root $rootPath -Wrapper (Join-Path $rootPath 'installers\WinSW-x64.exe')
        & (Join-Path $rootPath 'bliss-mfa\scripts\Stage-BlissProvider.ps1') -Root $rootPath
        Import-Certificate -FilePath (Join-Path $rootPath 'bliss-mfa\.local\engine\engine-cert.pem') -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
    }
    Repair {
        Initialize-Appliance
        $owned=Assert-OwnedService
        if (!$owned) {
            & (Join-Path $rootPath 'bliss-mfa\scripts\Install-EngineService.ps1') -Root $rootPath -Wrapper (Join-Path $rootPath 'installers\WinSW-x64.exe')
            Run-Checked $serviceExe @('stop')
        }
        $provider='Registry::HKEY_CLASSES_ROOT\CLSID\{FCEFDFAB-B0A1-4C4D-8B2B-4FF4E0A3D978}'
        if (!(Test-Path $provider)) {
            & (Join-Path $rootPath 'bliss-mfa\scripts\Stage-BlissProvider.ps1') -Root $rootPath
        } elseif ((Get-ItemProperty $provider).login_text -ne 'Bliss MFA') {
            throw 'Different credential-provider configuration detected; repair refused.'
        }
        else {
            & (Join-Path $rootPath 'bliss-mfa\scripts\Stage-BlissProvider.ps1') -Root $rootPath -Repair
        }
        Import-Certificate -FilePath (Join-Path $rootPath 'bliss-mfa\.local\engine\engine-cert.pem') -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
    }
    Ready {
        $config=Get-Content (Join-Path $rootPath 'bliss-mfa\.local\engine\config.json') -Raw | ConvertFrom-Json
        $appliance=Get-Content (Join-Path $rootPath 'bliss-mfa\.local\engine\appliance.json') -Raw | ConvertFrom-Json
        $ready=$false
        for ($attempt=0;$attempt -lt 60;$attempt++) {
            try {
                $a=Invoke-RestMethod ('http://127.0.0.1:'+$config.adapter_port+'/health') -TimeoutSec 2
                $b=Invoke-RestMethod ('http://127.0.0.1:'+$appliance.api_port+'/health') -TimeoutSec 2
                $c=Invoke-RestMethod ('https://localhost:'+$config.auth_port+'/health') -TimeoutSec 2
                $d=Invoke-WebRequest ('https://localhost:'+$appliance.tls_port+'/login') -UseBasicParsing -TimeoutSec 2
                $agent=Invoke-RestMethod ('http://127.0.0.1:'+$appliance.agent_port+'/health') -Headers @{Authorization=('Bearer '+$appliance.agent_token)} -TimeoutSec 2
                if ($a.status -eq 'ok' -and $b.status -eq 'ok' -and $c.status -eq 'ok' -and $d.StatusCode -eq 200 -and $agent.status -eq 'ok') { $ready=$true;break }
            } catch { Start-Sleep -Seconds 1 }
        }
        if (!$ready) { throw 'Installed appliance readiness failed; rollback required.' }
        $uninstallKey='HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\BlissMFA'
        if (Test-Path $uninstallKey) {
            $release=Get-Content (Join-Path $rootPath 'release.json') -Raw | ConvertFrom-Json
            Set-ItemProperty $uninstallKey -Name DisplayVersion -Value $release.version
        }
    }
    Integration {
        if (!$ControlRoot) { throw 'Protected updater control directory required.' }
        $menu=Join-Path ([Environment]::GetFolderPath('CommonPrograms')) 'Bliss MFA'
        New-Item -ItemType Directory -Path $menu -Force | Out-Null
        $shell=New-Object -ComObject WScript.Shell
        foreach ($item in @(@('Check for Bliss MFA updates','update'),@('Repair Bliss MFA','repair'))) {
            $link=$shell.CreateShortcut((Join-Path $menu ($item[0]+'.lnk')))
            $link.TargetPath=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
            $link.Arguments='-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $ControlRoot 'Setup-BlissMFA.ps1')+'" -Action '+$item[1]+' -Root "'+$rootPath+'"'
            $link.Save()
        }
        Set-Content -LiteralPath (Join-Path $menu 'Bliss MFA Portal.url') -Encoding ASCII -Value "[InternetShortcut]`r`nURL=https://localhost:19443"
        [ordered]@{Root=$rootPath;ControlRoot=$ControlRoot;Version=(Get-Content (Join-Path $rootPath 'release.json') -Raw | ConvertFrom-Json).version} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ControlRoot 'windows_installer\installation.json')
        $key='HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\BlissMFA'
        New-Item $key -Force | Out-Null
        $values=@{DisplayName='Bliss MFA';Publisher='Bliss IT Solutions Inc.';InstallLocation=$rootPath;DisplayVersion=(Get-Content (Join-Path $rootPath 'release.json') -Raw | ConvertFrom-Json).version;UninstallString=('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $ControlRoot 'windows_installer\Uninstall-BlissMFA.ps1')+'"');ModifyPath=('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $ControlRoot 'Setup-BlissMFA.ps1')+'" -Action repair -Root "'+$rootPath+'"')}
        foreach ($entry in $values.GetEnumerator()) { New-ItemProperty $key -Name $entry.Key -Value $entry.Value -PropertyType String -Force | Out-Null }
        if ($AutomaticUpdates) {
            $executable=Join-Path $ControlRoot 'python\python.exe'
            $arguments='"'+(Join-Path $ControlRoot 'windows_installer\manager.py')+'" update --root "'+$rootPath+'"'
            $taskAction=New-ScheduledTaskAction -Execute $executable -Argument $arguments
            $trigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(10) -RepetitionInterval (New-TimeSpan -Hours 6)
            $principal=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
            $settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
            Register-ScheduledTask -TaskName 'BlissMFA-Updates' -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
        }
    }
}
