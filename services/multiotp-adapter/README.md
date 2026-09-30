# multiOTP Adapter

Narrow integration boundary between Bliss Secure MFA and multiOTP.

## Rules

- Prefer supported native multiOTP API operations.
- Use controlled CLI/library fallbacks only for capabilities not available through the native API.
- Never accept raw commands from callers.
- Never log token seeds, provisioning URIs, PINs, passwords, or recovery codes.
- Every mutating operation must carry an audit correlation ID.

## CLI result contract (multiOTP 5.10.2.2)

Success codes are specific to the operation: create, enable, disable and unlock
use 11; delete uses 12; resync uses 14; provisioning uses 17; lists and token
removal use 19. OTP verification accepts only 0. Delete also accepts missing-user
code 21 because repeated deletion must converge to an absent engine identity.
Other informational codes must never be accepted as authentication success.

`revoke` first deactivates the identity, then removes/rotates its token. The
response includes `authentication_disabled` once deactivation succeeds. If the
subsequent removal fails or times out, `ok` remains false and the appliance must
record revoked access, release the seat, and audit the incomplete operation.
Revoked users cannot be enabled, unlocked, or changed to disabled to bypass
revocation; delete and create/enroll a new identity to restore access.

The engine companion fixes are required: software token removal must not try to
write an empty token record, replacement clears the prior token clock/cache, and
assignment must validate that the user and token exist before changing either.
Do not deploy the adapter code while assuming an unpatched engine's removal is
atomic; the disabled-state response is the recovery signal for a partial failure.

Run adapter regression tests with `python -m pytest` from this directory after
installing the project development dependencies.
