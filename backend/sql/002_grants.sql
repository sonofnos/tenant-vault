-- Runs after 001_schema.sql creates the tables. tenant_vault_app gets exactly
-- the privileges the application needs and nothing else: no DDL rights, no
-- ownership, so it cannot alter or drop a policy even if application code
-- were compromised into trying.
GRANT USAGE ON SCHEMA public TO tenant_vault_app;
GRANT SELECT ON roles TO tenant_vault_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON organizations, users, records, audit_log, webhook_events, jobs TO tenant_vault_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tenant_vault_app;
