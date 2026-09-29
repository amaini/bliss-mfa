# multiOTP Integration Discovery

## Current engine

Repository: `amaini/multiotp_Bliss`

Observed upstream engine version: multiOTP 5.10.2.2.

The existing server layer exposes multiple interfaces, including:

- web UI
- XML service
- SOAP service
- Vue-oriented API path triggered with `Prefer: api=vuejs`

Relevant entry points observed in `multiotp.server.php`:

```php
$multiotp->ApiVueJsPreAuth();
$multiotp->ApiVueJs($postdata);
```

## Phase 0 objective

Map the native API before introducing CLI wrappers.

For each required portal action determine:

| Capability | Native API | CLI/library fallback | Notes |
|---|---|---|---|
| List users | TBD | TBD | |
| Read user | TBD | TBD | |
| Create user | TBD | TBD | |
| Activate/deactivate | TBD | TBD | |
| Lock/unlock | TBD | TBD | |
| Begin TOTP enrollment | TBD | TBD | |
| Verify enrollment | TBD | TBD | |
| Replace token/device | TBD | TBD | |
| Revoke token/device | TBD | TBD | |
| Resync token | TBD | TBD | |
| Recovery/scratch codes | TBD | TBD | |
| Authentication status | TBD | TBD | |
| Audit/auth events | TBD | TBD | |

## Adapter policy

The adapter will normalize multiOTP behavior into stable Bliss-domain operations. Portal code must not depend directly on multiOTP-specific request formats or CLI syntax.

Any CLI fallback must:
- use fixed executable and fixed argument templates
- reject unexpected arguments
- avoid `shell=True`
- capture structured exit status
- redact sensitive output
- use explicit timeouts
- generate an audit correlation ID
