-- Multi-tenant schema. Every tenant table carries org_id and an RLS policy
-- that compares it to current_setting('app.current_org_id'). App-level
-- WHERE org_id = :org_id filters are still written everywhere they're needed
-- for query planning, but RLS is the backstop: a filter a developer forgot to
-- write cannot leak a row, because Postgres itself refuses to return it.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE organizations (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name       text        NOT NULL,
    slug       text        NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);
-- Deliberately NOT row-level-secured: this table has no org_id to scope by,
-- and it's only ever read/written through platform-level session (org_id=None).
-- `slug` exists so login can resolve an org before a tenant context is known
-- without ever querying a tenant table (users, in particular) outside RLS --
-- see backend/app/auth/routes.py for why that matters.

CREATE TABLE roles (
    id          smallint PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    description text
);
INSERT INTO roles (id, name, description) VALUES
    (1, 'admin',  'Full access within the organization, including deleting records'),
    (2, 'member', 'Can create and read records, cannot delete'),
    (3, 'viewer', 'Read-only');

CREATE TABLE users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid        NOT NULL REFERENCES organizations(id),
    email         text        NOT NULL,
    password_hash text        NOT NULL,
    role_id       smallint    NOT NULL REFERENCES roles(id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, email)
);
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY; -- applies even to the table owner
CREATE POLICY tenant_isolation ON users
    USING (org_id = current_setting('app.current_org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid);

-- The core resource. Themed on healthcare intake without claiming any
-- specific clinical data model or certification -- the point demonstrated is
-- the isolation and audit boundary, which is the same problem for any
-- sensitive-record SaaS product.
CREATE TABLE records (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid        NOT NULL REFERENCES organizations(id),
    created_by   uuid        NOT NULL REFERENCES users(id),
    subject_name text        NOT NULL,
    notes        text        NOT NULL,
    status       text        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'reviewed', 'closed')),
    ai_summary   text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE records ENABLE ROW LEVEL SECURITY;
ALTER TABLE records FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON records
    USING (org_id = current_setting('app.current_org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid);
CREATE INDEX idx_records_org_created ON records (org_id, created_at DESC);

-- Append-only. Every mutating action on a tenant table is recorded here for
-- auditability, independent of whether the mutation itself succeeded in
-- being "correct" -- an audit trail records what happened, not what should
-- have happened.
CREATE TABLE audit_log (
    id         bigserial PRIMARY KEY,
    org_id     uuid        NOT NULL REFERENCES organizations(id),
    actor_id   uuid        NOT NULL,
    action     text        NOT NULL,
    entity     text        NOT NULL,
    entity_id  uuid,
    metadata   jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON audit_log
    USING (org_id = current_setting('app.current_org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid);

-- Webhook deliveries received from external systems. Keyed by the sender's
-- event id so a retried delivery is dropped, not reprocessed.
CREATE TABLE webhook_events (
    event_id    text PRIMARY KEY,
    org_id      uuid        NOT NULL REFERENCES organizations(id),
    event_type  text        NOT NULL,
    payload     jsonb       NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON webhook_events
    USING (org_id = current_setting('app.current_org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid);

-- Background job queue. A worker claims rows with SKIP LOCKED so several
-- workers can run at once without double-processing the same job.
CREATE TABLE jobs (
    id           bigserial PRIMARY KEY,
    org_id       uuid        NOT NULL REFERENCES organizations(id),
    job_type     text        NOT NULL,
    payload      jsonb       NOT NULL,
    status       text        NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'failed')),
    attempts     int         NOT NULL DEFAULT 0,
    last_error   text,
    run_after    timestamptz NOT NULL DEFAULT now(),
    created_at   timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON jobs
    USING (org_id = current_setting('app.current_org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid);
CREATE INDEX idx_jobs_pending ON jobs (run_after) WHERE status = 'pending';
