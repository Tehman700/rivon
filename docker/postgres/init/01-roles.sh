#!/bin/sh
# Runs once, on first start of an empty data volume.
#
# rivon_owner  owns the databases and schema; Alembic connects as it.
# rivon_app    is what the API and workers use: not a superuser, not the table
#              owner, no BYPASSRLS. Combined with FORCE ROW LEVEL SECURITY this
#              guarantees the tenant policies apply to every app query.
# rivon_relay  is the outbox relay. It reads events across tenants, so it gets
#              a role-specific policy on outbox_events and no grants on any
#              other table (see migration 0004).
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v owner_pw="$RIVON_DB_OWNER_PASSWORD" -v app_pw="$RIVON_DB_APP_PASSWORD" \
  -v relay_pw="$RIVON_DB_RELAY_PASSWORD" <<'SQL'
CREATE ROLE rivon_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'owner_pw';
CREATE ROLE rivon_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'app_pw';
CREATE ROLE rivon_relay LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'relay_pw';
CREATE DATABASE rivon OWNER rivon_owner;
CREATE DATABASE rivon_test OWNER rivon_owner;
SQL

for db in rivon rivon_test; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<'SQL'
ALTER SCHEMA public OWNER TO rivon_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO rivon_app, rivon_relay;
-- Tables Alembic creates later are usable (DML only) by the app role.
ALTER DEFAULT PRIVILEGES FOR ROLE rivon_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rivon_app;
ALTER DEFAULT PRIVILEGES FOR ROLE rivon_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO rivon_app;
SQL
done
