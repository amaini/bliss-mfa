#!/bin/sh
set -eu
# Read passwords from private files; never echo them or enable shell tracing.
app_password=$(cat /run/secrets/postgres_app_password)
test -n "$app_password"
export BLISS_APP_PASSWORD="$app_password"
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 <<'SQL'
\getenv app_password BLISS_APP_PASSWORD
CREATE ROLE bliss_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE bliss_license TO bliss_app;
GRANT USAGE, CREATE ON SCHEMA public TO bliss_app;
SQL
