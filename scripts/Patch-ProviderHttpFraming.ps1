# Add complete HTTP response framing to the installed native PHP client.
[CmdletBinding()]
param([string]$ProviderRoot='C:\Program Files\multiOTP', [string]$BackupRoot='C:\BlissMFA\provider-backup')
$ErrorActionPreference='Stop'
$file=Join-Path $ProviderRoot 'php\multiotp.windows.php'
$text=[IO.File]::ReadAllText($file).Replace("`r`n","`n")
$marker='// A complete Content-Length response does not require a TLS EOF.'
$readMarker='// Read exactly the framed body without waiting for a TLS EOF.'
if ($text.Contains($marker) -and $text.Contains($readMarker)) { Write-Output 'HTTP framing and byte-read patches already applied'; return }
$anchor='                      // No flush, as we are not dislaying anything in the process'
if (!$text.Contains($marker) -and ($text.Split(@($anchor),[StringSplitOptions]::None).Count - 1) -ne 1) { throw 'Unexpected provider client source; refusing ambiguous patch.' }
$insert=@'
                      // A complete Content-Length response does not require a TLS EOF.
                      // Some HTTPS servers keep the stream open after the body.
                      $reply_header_end = mb_strpos($reply, "\r\n\r\n");
                      if (FALSE !== $reply_header_end) {
                          $reply_header = mb_substr($reply, 0, $reply_header_end)."\r\n";
                          if (preg_match('/\r\nContent-Length:\s*([0-9]+)\s*\r\n/i', $reply_header, $length_match)) {
                              $expected_body_length = intval($length_match[1]);
                              if (strlen($reply) - $reply_header_end - 4 >= $expected_body_length) {
                                  $reply = substr($reply, 0, $reply_header_end + 4 + $expected_body_length);
                                  $info['timed_out'] = FALSE;
                                  break;
                              }
                          }
                      }
'@
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
$backup=Join-Path $BackupRoot 'multiotp.windows.before-http-framing.php'
if (!(Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $file -Destination $backup }
$rollback=Join-Path $BackupRoot 'multiotp.windows.before-exact-body-read.php'
if (Test-Path -LiteralPath $rollback) { throw 'Exact-body-read recovery point already exists; inspect before retrying.' }
Copy-Item -LiteralPath $file -Destination $rollback
if (!$text.Contains($marker)) { $text=$text.Replace($anchor,$insert+"`n"+$anchor) }
$oldRead='                      // Read available bytes; the final XML line need not end with a newline.'+"`n"+'                      $reply.= fread($fp, 8192);'
if ($text.Contains($oldRead)) { $text=$text.Replace($oldRead,'                      $reply.= fgets($fp, 1024);') }
$lastAnchor="`n"+'                  $last_length = 0;'
if (($text.Split(@($lastAnchor),[StringSplitOptions]::None).Count - 1) -ne 1) { throw 'Unexpected native read initialization.' }
$text=$text.Replace($lastAnchor,$lastAnchor+"`n"+'                  $expected_reply_length = NULL;')
$lengthAnchor='                              $expected_body_length = intval($length_match[1]);'
if (($text.Split(@($lengthAnchor),[StringSplitOptions]::None).Count - 1) -ne 1) { throw 'Unexpected body length parsing.' }
$text=$text.Replace($lengthAnchor,$lengthAnchor+"`n"+'                              $expected_reply_length = $reply_header_end + 4 + $expected_body_length;')
$readAnchor="`n"+'                      $reply.= fgets($fp, 1024);'
if (($text.Split(@($readAnchor),[StringSplitOptions]::None).Count - 1) -ne 1) { throw 'Unexpected native HTTP read loop.' }
$readBlock=@'
                      // Read exactly the framed body without waiting for a TLS EOF.
                      if (NULL === $expected_reply_length) {
                          $reply.= fgets($fp, 1024);
                      } else {
                          $remaining_reply_length = $expected_reply_length - strlen($reply);
                          if ($remaining_reply_length <= 0) { break; }
                          $reply.= fread($fp, min(8192, $remaining_reply_length));
                      }
'@
$text=$text.Replace($readAnchor,"`n"+$readBlock)
[IO.File]::WriteAllText($file,$text,(New-Object Text.UTF8Encoding($false)))
& (Join-Path $ProviderRoot 'php\php.exe') -l $file
if ($LASTEXITCODE -ne 0) { Copy-Item -LiteralPath $rollback -Destination $file -Force; throw 'Patched client failed syntax verification.' }
Write-Output 'Native client HTTP framing and byte-read patches applied'
