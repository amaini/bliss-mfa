# SQLite to PostgreSQL cutover — deployment-agent runbook

This changes only the hosted licensing/account backend. Client appliances keep
their local databases. PostgreSQL does not resolve email configuration or replace
payment/installer/RDP acceptance. Do not open client purchases until those pass.

The Portainer stack now uses PostgreSQL 17 on an internal Docker network and a
non-superuser `bliss_app` login. It reads separate administrator and app passwords
from private files. The application waits for a verified import marker before
serving traffic. No port 5432 is published.

## Prepare without changing the running service

1. Pull current `main` from https://github.com/amaini/bliss-mfa on the Docker-host
   LXD container. Record the running backend's image ID, stack YAML, environment,
   signing key, and SQLite volume name. Keep this rollback material private.
   Do not delete the old volume or overwrite the old image tag.
2. Build the new image from `apps/license-server`:

   ```sh
   docker build -t bliss-license:postgres-v1 /opt/bliss-mfa/source
   ```

   Here `/opt/bliss-mfa/source` must contain the UPDATED license-server Dockerfile,
   pyproject.toml, and license_server directory, not the repository root.
3. Save `deployment/hosted/init-postgres.sh` to
   `/opt/bliss-mfa/source-deployment/init-postgres.sh` with Unix LF line endings.
   Prepare distinct random passwords in private files. On the Docker host:

   ```sh
   umask 077
   mkdir -p /opt/bliss-mfa/private /opt/bliss-mfa/migration
   openssl rand -hex 32 > /opt/bliss-mfa/private/postgres-admin-password
   openssl rand -hex 32 > /opt/bliss-mfa/private/postgres-app-password
   pg_gid=$(docker run --rm --entrypoint id postgres:17 -g postgres)
   chown root:"$pg_gid" /opt/bliss-mfa/private/postgres-admin-password /opt/bliss-mfa/private/postgres-app-password
   chmod 640 /opt/bliss-mfa/private/postgres-admin-password /opt/bliss-mfa/private/postgres-app-password
   ```

   Run password generation once. PostgreSQL init scripts run only for a fresh
   data volume; changing a file later does not rotate a database password.
   Keep the private directory mode 0700. Compose file-backed secrets preserve
   host file permissions, so PostgreSQL's container group needs read permission
   for the initialization script. The app container runs as root and can read
   its mounted password file. Do not publish either password file.
4. Preserve Stripe/Resend/admin settings and the existing signing key/release
   mounts. The new stack overrides DATABASE_URL and DATABASE_PASSWORD_FILE and
   sets REQUIRE_SQLITE_IMPORT=true. Do not remove that guard for an existing site.

## Freeze writes and take a consistent snapshot

Schedule a short maintenance window; stop new checkouts and the existing backend
container. Capture the LAST SQLite state after stopping the writer. Stop only
the backend service, leaving WordPress and other VPS services available.
Use the actual old SQLite volume name in place of `OLD_SQLITE_VOLUME`:

```sh
docker run --rm --entrypoint python \
  -v OLD_SQLITE_VOLUME:/source:ro \
  -v /opt/bliss-mfa/migration:/transfer \
  bliss-license:postgres-v1 -c "import sqlite3; s=sqlite3.connect('file:/source/licenses.db?mode=ro',uri=True); d=sqlite3.connect('/transfer/accounts.sqlite'); s.backup(d); d.close(); s.close()"
chmod 600 /opt/bliss-mfa/migration/accounts.sqlite
```

This uses SQLite's backup API, preserving committed WAL data if present. Keep a
protected off-VPS copy of the snapshot and signing key. Check that the snapshot
was produced successfully; do not proceed on errors. Keep the original volume.

## Deploy PostgreSQL, then import

Update the existing Portainer stack using `portainer-stack.yaml`. PostgreSQL
should become healthy. The application will exit/retry with “verified SQLite
import is required”; this is deliberate maintenance, not readiness. If the new
container is empty but serves customer registration, stop it and check the guard.

Confirm the new database network name in Portainer (normally
`bliss-license_database`), then run the importer on the Docker endpoint:

```sh
docker run --rm --network bliss-license_database \
  --entrypoint python \
  -e DATABASE_URL=postgresql+psycopg://bliss_app@postgres:5432/bliss_license \
  -e DATABASE_PASSWORD_FILE=/run/secrets/postgres_app_password \
  -v /opt/bliss-mfa/private/postgres-app-password:/run/secrets/postgres_app_password:ro \
  -v /opt/bliss-mfa/migration/accounts.sqlite:/transfer/accounts.sqlite:ro \
  bliss-license:postgres-v1 -m license_server.import_sqlite \
  --source /transfer/accounts.sqlite --confirm-maintenance
```

Expected result: `verified: true` and per-table row counts. The tool opens the
snapshot read-only, validates its version/columns/integrity/foreign keys, refuses
existing destination rows or unexpected tables, copies in one transaction, and
compares all transferred values including hashes and UTC timestamps. Failure
rolls back copied rows. It never prints account data or secrets. An empty INITIAL
schema can remain after failure; a successful import cannot be rerun over itself.
Do not work around an error by deleting tables or using an empty source snapshot.

After success, restart the backend service in Portainer. Keep the same signing
key; replacing it would invalidate existing clients. Verify PostgreSQL's app user
has no superuser/role/database-creation privileges and the DB port is not public.

## Accept before opening sales

- `/health` responds, existing registered account can sign in, and verified status
  and license/purchase ownership are preserved. Public health alone is insufficient.
- Resend sends a verification email to a real inbox; verify it and sign in.
- Stripe displays the intended one-seat live monthly price. A deliberately
  authorized purchase produces signed deliveries and exactly one active license.
- Paid installer download, activation, clean Windows install and RDP acceptance pass.
- Restart the stack and confirm the account/license remains present.

## Back up and prove restoration

Use PostgreSQL's consistent logical dump instead of copying its live data folder:

```sh
umask 077
docker exec POSTGRES_CONTAINER pg_dump -U postgres -d bliss_license -Fc > /opt/bliss-mfa/migration/licenses-postgres.dump
```

Check exit status and a nonempty dump. Schedule regular encrypted off-VPS copies,
and test `pg_restore --no-owner --no-privileges` into a separate clean test database
owned by its test app login. Never restore over the live database as a test.
Verify accounts, licenses and ownership there. Keep private password files and
signing key backed up separately. PostgreSQL volume persistence is not a backup.

## Rollback boundary

Before accepting any new writes on PostgreSQL, rollback can restore the previous
stack/image/environment pointing to the untouched SQLite volume. Stop the new
backend first. Keep PostgreSQL data for investigation. After new PostgreSQL writes,
simply switching back would lose those writes: require an explicit reconciliation
and recovery plan instead. Never run both backends accepting writes in parallel.

References: [SQLAlchemy psycopg support](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg),
[official PostgreSQL container](https://hub.docker.com/_/postgres),
[PostgreSQL backups](https://www.postgresql.org/docs/current/backup-dump.html).
