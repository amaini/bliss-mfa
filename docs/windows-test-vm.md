# Standing Windows test target

On 4 October 2026, the user authorized WIN-10VM-ASUS for all kinds of project
tests indefinitely, and instructed that this repository be verified on that VM.
Installation, upgrade, rollback, reboot, authentication and recovery tests on
this target are authorized. This permission does not designate the laptop or
customer production machines as disposable test targets.

## Verified target identity

- Expected computer name: `WIN-10VM-ASUS`.
- Tailscale endpoint: `100.83.112.5`.
- Controller laptop Tailscale address observed: `100.68.167.45`.
- WinRM HTTP port: 5985, NTLM with message encryption.
- Administrator credentials already exist in the primary checkout's ignored
  `.local/rdp-target.json`; do not put credentials in Git, logs or arguments.
- The existing native remoting helper checks the expected computer name before
  executing scripts. Use that guard for every mutation.

Initial authenticated inspection after access restoration confirmed Windows 10
Pro build 19045, administrator execution, the running automatic BlissMFAEngine
service, and installed application version 0.1.1. Both standard WinRM firewall
rules were scoped to the controller Tailscale address. Update-key provisioning
in Program Files was absent. These observations are a baseline, not release
acceptance or proof of operating-system security-update coverage.

## Current release acceptance

Test the exact candidate recorded in `pilot-release-0.1.2-validation.md` and
`deployment/hosted/PILOT-0.1.2.md`. Preserve the existing 0.1.1 state to test real
upgrade and rollback before establishing a separate fresh-install result.
Capture configuration and enrollment fingerprints and a recoverable private
snapshot before modifying the installed service. Keep a working administrator
recovery route independent of the credential provider under test.

Record the actual installer/update hashes, OS build, provider version, service
state and evidence for every result. Native OTP/password component checks do not
prove an interactive desktop/RDP login. Existing installed files do not prove a
clean installation. A restored network connection does not prove any release
test has run.

The first inspection succeeded, but subsequent authenticated WinRM commands
timed out while unauthenticated HTTP remained reachable. No 0.1.2 installation
or MFA change had been applied at that point. An administrator WinRM restart was
requested. Complete the release checks after authenticated execution recovers.
