# multiOTP Adapter

Narrow integration boundary between Bliss Secure MFA and multiOTP.

## Rules

- Prefer supported native multiOTP API operations.
- Use controlled CLI/library fallbacks only for capabilities not available through the native API.
- Never accept raw commands from callers.
- Never log token seeds, provisioning URIs, PINs, passwords, or recovery codes.
- Every mutating operation must carry an audit correlation ID.

Phase 0 will define the capability matrix before implementation.
