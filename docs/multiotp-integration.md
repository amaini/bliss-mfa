# multiOTP Integration Discovery

## Current engine

Repository: `amaini/multiotp_Bliss`

Observed upstream engine version: multiOTP 5.10.2.2.

The existing server layer exposes multiple interfaces:

- legacy web administration surface
- XML service
- SOAP/OpenOTP-compatible authentication service
- Vue-oriented API path triggered with `Prefer: api=vuejs`

Relevant entry points observed in `multiotp.server.php`:

```php
$multiotp->ApiVueJsPreAuth();
$multiotp->ApiVueJs($postdata);
```

The SOAP/WSDL surface is authentication-oriented only (login/challenge/status), so it is not sufficient as the management plane for Bliss Secure MFA.

## Confirmed legacy management surface

The current web administration endpoint already exposes authenticated remote methods after an admin session is established.

Confirmed methods include:

- `GetUsersList`
- `GetEnhancedUsersList`
- `GetLockedUsersList`
- `GetDelayedUsersList`
- `GetTokensList`
- `FastCreateUser`
- `DeleteUser`
- `DeleteToken`
- `UnlockUser`
- `ResyncUser`
- `CheckToken`
- `PrintQrCode`
- `PrintScratchlist`

These methods are useful proof that the underlying PHP class already provides the required primitives. However, the legacy web-admin transport is not suitable as the long-term Bliss portal integration because it is session/cookie-oriented, uses tab-delimited option payloads, and was designed for the bundled admin UI rather than a separate multi-tenant management plane.

## Confirmed CLI/library primitives

The repository documentation confirms these supported commands:

- `-fastcreate`, `-fastcreatenopin`, `-fastcreatewithpin`
- `-createga`
- `-create`
- `-qrcode`
- `-urllink`
- `-scratchlist`
- `-resync`
- `-update-pin`
- `-assign-token`
- `-remove-token`
- `-[des]activate`
- `-[un]lock`
- `-delete`
- `-user-info`

These give us a reliable fallback where a supported native management API operation cannot be used.

## Capability matrix

| Bliss capability | Confirmed existing primitive | Preferred adapter route | Status |
|---|---|---|---|
| List users | `GetUsersList`, `GetEnhancedUsersList` | Native API/class | Confirmed primitive |
| Read user | `-user-info` and class methods | Native API/class | Confirmed primitive |
| Create TOTP user | `FastCreateUser`, `-fastcreate*`, `-createga` | Native API/class | Confirmed primitive |
| Activate/deactivate | `-[des]activate` | Native API/class if exposed, CLI fallback | Confirmed primitive |
| Unlock user | `UnlockUser`, `-[un]lock` | Native API/class | Confirmed primitive |
| Detect locked/delayed users | `GetLockedUsersList`, `GetDelayedUsersList` | Native API/class | Confirmed primitive |
| Generate QR provisioning | `PrintQrCode`, `-qrcode`, `-urllink` | Native API/class | Confirmed primitive |
| Verify enrollment OTP | `CheckToken` | Native API/class | Confirmed primitive |
| Resync token | `ResyncUser`, `-resync` | Native API/class | Confirmed primitive |
| Recovery/scratch codes | `PrintScratchlist`, `-scratchlist` | Native API/class | Confirmed primitive |
| Remove assigned token | `-remove-token` | Native API/class if exposed, CLI fallback | Confirmed primitive |
| Assign imported token | `-assign-token` | Native API/class if exposed, CLI fallback | Confirmed primitive |
| Delete user | `DeleteUser`, `-delete` | Native API/class | Confirmed primitive |
| Delete token | `DeleteToken`, `-delete-token` | Native API/class | Confirmed primitive |
| Authentication health/status | SOAP `openotpStatus`, token-check primitives | Native API | Confirmed |
| Authentication event/audit feed | Not yet confirmed | TBD | Open |

## Important implementation conclusion

We do **not** need to make the Bliss API execute arbitrary shell commands.

The underlying multiOTP PHP class already contains most lifecycle primitives. The preferred design is therefore:

```text
Bliss API
   |
   v
multiOTP Adapter
   |
   +--> supported native/class operation
   |
   +--> fixed CLI fallback only where needed
```

The adapter should present stable domain-level operations such as:

```text
list_users()
get_user()
create_totp_user()
begin_enrollment()
verify_enrollment()
replace_device()
revoke_device()
disable_user()
enable_user()
unlock_user()
resync_user()
generate_recovery_codes()
delete_user()
```

## Enrollment design

The existing multiOTP primitives support the required flow:

1. Create the user/token.
2. Obtain QR/provisioning material.
3. Present provisioning material through a short-lived Bliss enrollment transaction.
4. User enters a generated OTP.
5. Adapter verifies it using `CheckToken`.
6. Bliss marks the enrollment complete.

The Bliss database must not persist the token seed or raw provisioning URI.

## Device replacement design

Device replacement should be treated as an atomic workflow at the Bliss layer:

1. Verify the operator is authorized.
2. Record the replacement reason.
3. Revoke/remove the old token.
4. Create new token/enrollment material.
5. Verify the new OTP.
6. Mark the new device active.
7. Write an audit event.

If replacement fails after revocation, the workflow must leave the account in an explicit recoverable state rather than silently reporting success.

## Legacy admin endpoint assessment

The bundled web administration endpoint is useful for discovery and compatibility testing but should **not** become the public Bliss backend contract.

Reasons:

- admin-session oriented
- single-admin model
- no tenant concept
- tab-delimited request options
- some state-changing calls can be invoked via the legacy remote-call pattern
- no Bliss RBAC/audit semantics
- exposes HTML-producing QR/scratch-list operations rather than clean domain objects

We should isolate this interface behind the adapter if it is used at all.

## Vue API status

The server clearly dispatches to `ApiVueJsPreAuth()` and `ApiVueJs()`, but the implementation lives inside the large generated/combined multiOTP class artifact and still needs runtime or source-level extraction before we can document its exact request schema safely.

Until that is mapped, the implementation plan should not assume that the Vue API is stable enough to be our public integration contract.

## Adapter policy

The adapter will normalize multiOTP behavior into stable Bliss-domain operations. Portal code must not depend directly on multiOTP request formats or CLI syntax.

Any CLI fallback must:

- use a fixed executable
- use fixed argument templates per operation
- pass arguments as an array, never through shell interpolation
- reject unexpected arguments
- avoid `shell=True`
- capture structured exit status
- redact sensitive output
- use explicit timeouts
- generate an audit correlation ID
- never log provisioning URIs, seeds, PINs, passwords, or recovery codes

## Next discovery step

Run the current multiOTP container in an isolated development environment and exercise the `Prefer: api=vuejs` interface read-only first.

The goal is to capture:

- authentication/session mechanism
- request/response schema
- user-list response
- user-detail response
- token-list response
- supported write operations

No production multiOTP instance should be used for this discovery.
