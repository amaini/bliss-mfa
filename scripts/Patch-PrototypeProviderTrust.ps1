$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'WIN-10VM-ASUS') { throw 'Wrong disposable VM.' }
$provider = 'C:\Program Files\multiOTP'
$script = "$provider\php\multiotp.windows.php"
$ini = "$provider\php\php.ini"
$backup = 'C:\BlissMFA\provider-backup'
if (Test-Path $backup) { throw 'Provider backup exists; inspect before patching again.' }
New-Item -ItemType Directory $backup | Out-Null
Copy-Item -LiteralPath $script -Destination "$backup\multiotp.windows.php"
Copy-Item -LiteralPath $ini -Destination "$backup\php.ini"
$content = [IO.File]::ReadAllText($script)
$regex = [regex]::new("('verify_peer(?:_name)?'\s*=>\s*)false")
# Only the two default native-XML settings; unrelated vendor transports remain as supplied.
$prefixEnd = $content.IndexOf("'disable_compression'", $content.IndexOf('_default_ssl_context = array('))
if ($prefixEnd -lt 0) { throw 'Expected native TLS context not found.' }
$prefix = $content.Substring(0,$prefixEnd)
if ($regex.Matches($prefix).Count -ne 2) { throw 'Unexpected native TLS defaults.' }
$patched = $regex.Replace($prefix, '${1}true') + $content.Substring($prefixEnd)
[IO.File]::WriteAllText($script,$patched,[Text.UTF8Encoding]::new($false))
Copy-Item 'C:\BlissMFA\bliss-mfa\.local\engine\engine-cert.pem' "$provider\php\bliss-engine-ca.pem"
[IO.File]::AppendAllText($ini,"`r`n; Bliss prototype: pin the local engine certificate.`r`nopenssl.cafile=`"C:\Program Files\multiOTP\php\bliss-engine-ca.pem`"`r`n",[Text.UTF8Encoding]::new($false))
& "$provider\php\php.exe" -l $script
if ($LASTEXITCODE -ne 0) { throw 'Patched provider PHP syntax failed.' }
[ordered]@{NativePeerVerification=$true;NativeHostnameVerification=$true;CA='Provider-local certificate file';MachineTrustChanged=$false;PatchedSHA256=(Get-FileHash $script).Hash} | ConvertTo-Json
