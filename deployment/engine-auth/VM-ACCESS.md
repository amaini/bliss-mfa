# Disposable VM access

The provided target is `100.83.112.5`. Read-only network probes confirmed RDP
3389 is reachable; WinRM 5985/5986 and SSH 22 were not reachable. This does not
establish Windows version, administrator rights, provider configuration, or MFA.
This controller's current Tailscale address is `100.68.167.45`.

The available Windows UI automation workflow does not support automated terminal
or authentication dialogs. Use a remote command channel for installation/testing.
No VM setup change has been made by the agent.

## One-time user preparation

1. Sign into the disposable VM through RDP yourself. Confirm an independent console
   or checkpoint recovery route. Copy `scripts/Prepare-DisposableVm.ps1` into the VM.
2. Run the helper with no arguments in PowerShell. This only prints Windows build,
   computer name, expected Tailscale address presence, and provider registration.
3. If WinRM is the chosen command channel, run in an Administrator PowerShell:

```powershell
.\Prepare-DisposableVm.ps1 -ConfigureWinRM -ExpectedComputerName 'NAME-FROM-INVENTORY' -RecoveryConfirmed
```

The configure operation checks the computer name and target Tailscale address,
enables WinRM, and limits its default HTTP firewall rules to traffic from this
controller over the target Tailscale address. It keeps Basic authentication and
unencrypted WinRM messages disabled. No credential provider, account, RDP policy,
or host-side trust setting is changed. This script was syntax-checked, not executed
against the VM. If a command fails, inspect its output before retrying.

4. Supply the VM administrator username and password through the local ignored
   `.local/rdp-target.json` on this controller. Do not paste its contents into chat.
   Tell Codex when it is ready, and share the non-secret inventory/recovery details.

The command client will require encrypted NTLM messages inside Tailscale. We will
inspect the VM read-only and confirm identity before installing the provider.
SSH can be used instead if an existing SSH command channel is available.

The credential file contains sensitive data. Keep it local, exclude it from
backups/diagnostic uploads, and remove it after the disposable testing session.
