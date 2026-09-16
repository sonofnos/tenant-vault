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
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tenant_vault_app') THEN
        CREATE ROLE tenant_vault_app LOGIN PASSWORD 'app_password' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    END IF;
END
$$;
