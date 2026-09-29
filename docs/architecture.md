# Bliss Secure MFA Architecture

## Product boundary

Bliss Secure MFA is appliance-first. Every office gets an independent local
management plane. Authentication does not depend on Bliss cloud availability.

```text
Office administrator
       |
       v
127.0.0.1 / office LAN portal
       |
       v
Appliance API
  |         |
  |         +------> License Agent
  |                    |
  v                    | licensing / billing only
multiOTP Adapter       v
  |              license.blissitek.ca
  v
multiOTP
  |
FreeRADIUS
  |
Windows RDP / VPN
```

## Customer-local data

The appliance keeps locally:
- local administrator accounts and roles
- RDP/MFA user records
- enrollment workflow
- audit history
- multiOTP token state
- OTP secrets and provisioning material
- RADIUS traffic and authentication state

The central Bliss service stores only commercial and installation metadata:
license ID/type, installation ID/public key, RDP seat entitlement, subscription
state, last heartbeat, protected-seat count, software version and integrity
checkpoints.

## Billable RDP seat

One distinct Windows/RDP account enabled for Bliss Secure MFA protection equals
one Bliss RDP seat. Concurrent or reconnected sessions do not create extra
Bliss seats.

Seat-consuming states are pending enrollment, active and locked. Disabled,
revoked and deleted records do not consume a seat.

Microsoft RDS/CAL licensing remains separate.

## Online licensing

1. Bliss creates an online license and one-time activation code.
2. Appliance generates an Ed25519 installation keypair.
3. Activation binds the license to the installation ID/public key.
4. Bliss returns a signed lease.
5. Heartbeat uses a random challenge signed by the installation key.
6. The signed request contains seat count, software version and integrity signals.
7. Bliss returns a fresh signed lease.

The current code defaults to a 14-day lease and 30-day grace; both are
configuration values.

## Offline licensing

Offline licenses are explicitly issued as offline licenses.

1. Customer enters the offline activation code locally.
2. Appliance creates an installation code.
3. Bliss processes that code in the licensing control plane.
4. Bliss returns a signed activation response.
5. Appliance verifies the signature and installation binding.
6. The fixed-term entitlement works without Internet access.

Offline licensing is intended for annual/prepaid terms because ongoing online
validation is impossible in an air-gapped environment.

## Transfer

An online license normally requires a signed release from its bound appliance
before it can activate elsewhere. Bliss can force-release a failed appliance.

An offline installation cannot be remotely invalidated while disconnected.
Its old signed entitlement therefore remains technically valid until its signed
expiry if somebody retains the old appliance.

## Expiration policy

Licensing gates management rather than the RADIUS authentication path.
Restricted licensing prevents commercial management actions such as creating
or re-enabling protected users, but existing MFA authentication is not
automatically stopped solely because billing failed.

## Repository boundary

`amaini/multiotp_Bliss` remains the MFA/RADIUS engine.

`amaini/bliss-mfa` owns the appliance UI/API, local administrator RBAC,
licensing agent, seat enforcement, audit, central license server, billing
integration and the allow-listed multiOTP adapter.
