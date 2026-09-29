# Security Model

## Authentication-data boundary

multiOTP remains the owner of OTP/TOTP secret material. The central Bliss
license service does not require customer usernames, OTP seeds, QR codes,
passwords or RADIUS requests.

Provisioning URIs are returned only to the local management workflow and must
not be logged or centrally transmitted.

## Local management authentication

The appliance uses local roles: owner, admin, operator and readonly.

Initial setup is one-time and requires `SETUP_TOKEN`. Passwords are stored
with Argon2. Browser sessions use short-lived local JWTs carried in an HttpOnly
portal cookie.

Production appliances must use a unique random JWT secret and TLS.

## License cryptography

Each appliance generates an Ed25519 device keypair.

- the private key stays on the appliance
- the public key is registered with Bliss
- heartbeat and release requests are signed by the appliance key
- Bliss leases are signed by a separate Bliss signing key
- appliances contain only the Bliss public verification key

Changing a signed seat count, installation binding or expiry invalidates the
lease signature.

## Trusted time

The license agent persists the newest signed Bliss issue time it has observed.
The effective licensing clock cannot move earlier than that trusted value,
reducing simple clock-rollback bypasses.

## Installation-clone signals

The cryptographic device key is the primary installation identity. Heartbeats
also carry a hashed secondary machine fingerprint. A fingerprint change is
recorded as an anomaly rather than automatically treated as proof of abuse.

A later hardened build can store the installation key in TPM 2.0.

## Seat enforcement

The appliance API asks the local license agent before a protected RDP user is
created or re-enabled. The browser UI is not the security boundary.

The multiOTP adapter exposes only approved operations and never arbitrary shell
commands.

## Audit integrity

Local privileged operations form a hash chain. Every event stores its previous
event hash and its own digest. The appliance API exposes a local integrity
verification endpoint.

The current audit-head hash is included in licensing heartbeat metadata so Bliss
can checkpoint integrity without receiving the underlying customer events.

## Payment safety

License state may restrict management actions but is not wired directly into
RADIUS authentication. A failed card or temporary license-server outage must
not instantly lock an office out of an existing working MFA deployment.

## Air-gapped limitation

A truly air-gapped installation cannot be continuously policed from Bliss.
Offline entitlements therefore have a signed fixed expiry and should be sold as
prepaid terms. This is an explicit tradeoff rather than pretending a heartbeat
exists where no network path exists.
