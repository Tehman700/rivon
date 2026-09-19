-- Roles for a managed Postgres (Neon, RDS): the same split as
-- docker/postgres/init/01-roles.sh, minus creating databases.
--
-- Run once per environment, connected to the Rivon database as its owner:
--   psql "$RIVON_MIGRATION_DATABASE_URL" \
--     -v app_pw="..." -v relay_pw="..." -f scripts/bootstrap_managed_db.sql
--
-- The owner role (used only by Alembic) is whatever the provider created.
-- rivon_app  = API and workers: not the table owner, so RLS always applies.
-- rivon_relay = outbox relay: granted only what migration 0004 gives it.
-- Idempotent: safe to re-run, e.g. to rotate a password.

\set ON_ERROR_STOP on

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rivon_app') THEN
    CREATE ROLE rivon_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rivon_relay') THEN
    CREATE ROLE rivon_relay LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END
$$;

ALTER ROLE rivon_app PASSWORD :'app_pw';
ALTER ROLE rivon_relay PASSWORD :'relay_pw';

GRANT USAGE ON SCHEMA public TO rivon_app, rivon_relay;

-- Tables the migrations create later are usable (DML only) by the app role.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rivon_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO rivon_app;

-- Tables created before this script ran (e.g. a database migrated first).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rivon_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rivon_app;
