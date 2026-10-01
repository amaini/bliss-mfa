# Read-only activation diagnostics. Run as Administrator; prints no tokens or keys.
[CmdletBinding()]
param([string]$Root='C:\BlissMFA')
$ErrorActionPreference='Stop'
$configPath=Join-Path $Root 'bliss-mfa\.local\engine\appliance.json'
$config=Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$python=Join-Path $Root 'python\python.exe'
$code=@'
import hashlib,sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
k=serialization.load_pem_public_key(Path(sys.argv[1]).read_bytes())
print(hashlib.sha256(k.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest())
'@
$fingerprint=(& $python -c $code $config.public_key_file | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect installed public key' }
$report=[ordered]@{
    LicenseServer=$config.license_url
    InstalledPublicKeyFingerprint=$fingerprint
    LocalLeasePresent=(Test-Path -LiteralPath (Join-Path $config.license_state_dir 'lease.token'))
}
try {
    $health=Invoke-WebRequest -Uri ($config.license_url.TrimEnd('/')+'/health') -UseBasicParsing -TimeoutSec 20
    $report.ServerHealthHTTP=[int]$health.StatusCode
} catch { $report.ServerHealthError=$_.Exception.GetType().Name }
try {
    $state=Invoke-RestMethod -Uri ('http://127.0.0.1:'+ $config.agent_port +'/v1/status') -Headers @{Authorization=('Bearer '+$config.agent_token)} -TimeoutSec 20
    $report.AgentState=$state.state
    $report.ProtectedSeatLimit=$state.max_rdp_users
} catch { $report.AgentStatusError=$_.Exception.GetType().Name }
$log=Join-Path (Split-Path $configPath) 'license-agent.log'
if (Test-Path -LiteralPath $log) {
    $tail=Get-Content -LiteralPath $log -Tail 100
    $report.SignatureFailureInRecentLog=[bool]($tail -match 'Invalid Bliss license signature|InvalidSignature')
    $report.MissingSigningKeyInRecentLog=[bool]($tail -match 'signing.*key.*not configured')
}
$report | ConvertTo-Json
