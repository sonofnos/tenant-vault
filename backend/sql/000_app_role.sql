-- The role the application actually connects as. Migrations and schema
-- ownership stay with the superuser (the docker-compose/CI admin user);
-- this role owns nothing and has neither SUPERUSER nor BYPASSRLS.
--
-- This distinction is the whole point of the exercise. FORCE ROW LEVEL
-- SECURITY only binds the table *owner* -- it does nothing against a
-- superuser, which bypasses every RLS policy unconditionally regardless of
-- FORCE. A schema can have perfectly correct policies on every table and
-- still leak every row cross-tenant if the application connects as the
-- same role that owns the tables (as it does by default in most local
-- Postgres setups, including a fresh `postgres:16-alpine` container, whose
-- POSTGRES_USER is a superuser). The application must run as a separate,
-- deliberately weaker role for RLS to mean anything at all.
--
-- The password comes from the migration session (APP_DB_PASSWORD, set by
-- app/db/migrate.py), never from this file -- a public repo must not ship the
-- credential for a database that is reachable from the internet.
DO $$
DECLARE
    pw text := coalesce(nullif(current_setting('tenant_vault.app_password', true), ''), 'app_password');
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tenant_vault_app') THEN
        EXECUTE format('CREATE ROLE tenant_vault_app LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE', pw);
    ELSE
        EXECUTE format('ALTER ROLE tenant_vault_app PASSWORD %L', pw);
    END IF;
END
$$;
