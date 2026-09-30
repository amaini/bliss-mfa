# Deployment

## Customer appliance

The intended customer deployment contains:

- `appliance-portal`
- `appliance-api`
- `license-agent`
- real `multiotp-adapter`
- multiOTP / FreeRADIUS
- persistent local state and backups

The management portal should bind either:

1. to loopback only for server-console management, or
2. to a private office LAN interface / internal DNS name.

It must not be directly Internet-exposed.

The root `docker-compose.yml` is a development stack and deliberately uses the
development multiOTP mock. It is not a production manifest.

## First local development run

Generate a Bliss signing keypair:

```bash
python scripts/generate-license-keys.py
```

Then start the development stack:

```bash
docker compose up --build
```

The development portal is bound to:

```text
http://127.0.0.1:9443
```

Initialize the first owner at `/setup` with the development setup token from
the compose file.

## Production requirements

Before an office deployment:

- replace all development secrets
- use the real multiOTP adapter and validate its lifecycle commands
- put the local portal behind TLS
- restrict management network exposure
- back up appliance database and multiOTP state
- pin the Bliss public signing key
- supervise periodic online-license heartbeat
- use database migrations rather than development `create_all`
- configure log retention without secret/provisioning material
- test restore and server-replacement procedures

## Bliss central licensing

`apps/license-server` belongs on Bliss infrastructure, not on the customer's
appliance.

Its Ed25519 private signing key must not be distributed to customers. Customer
appliances receive only the public verification key.

Production central deployment also needs:

- PostgreSQL
- TLS
- restricted administrator API
- backups
- signing-key rotation procedure
- Stripe configuration when pricing is finalized
- monitoring and audit retention
