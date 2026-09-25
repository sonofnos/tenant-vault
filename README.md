# tenant-vault

A multi-tenant SaaS backend and admin UI: PostgreSQL Row-Level Security for organization isolation, RBAC, signed webhooks, a background job queue, and an AI-assisted feature. FastAPI, Next.js, Postgres.

**Live:** [vesta.sonofnos.com](https://vesta.sonofnos.com) (frontend, Vercel) · API on Render · Postgres on Neon. Sign up with any organisation slug to get your own isolated tenant; all data is synthetic.

Themed on healthcare intake records without claiming any clinical data model or compliance certification. The problem being demonstrated, an org's data must never be visible to another org even when application code has a bug, is the same for any SaaS product handling sensitive records, and it's the hardest security boundary to get right.

## The tenant-isolation story

Every tenant table (`users`, `records`, `audit_log`, `webhook_events`, `jobs`) has:

```sql
ALTER TABLE records ENABLE ROW LEVEL SECURITY;
ALTER TABLE records FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON records
    USING (org_id = current_setting('app.current_org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid);
```

`current_setting('app.current_org_id', true)` is set once per request, inside the same database transaction as every query that follows (see `app/db/session.py`), using `set_config(..., true)` so it never outlives that transaction. Application code still writes `WHERE org_id = :org_id` where it matters for query planning, but RLS is the actual backstop: a filter someone forgets to write cannot leak a row, because Postgres refuses to return it, not because the query happened to ask correctly.

**The bug this repo actually had, and the fix.** The first working version of this schema passed every test — until the tests ran against a database role that was a Postgres superuser. Superusers, and any role with `BYPASSRLS`, ignore RLS unconditionally, and `FORCE ROW LEVEL SECURITY` only binds the *table owner* against its own policies — it does nothing against a superuser. The official `postgres` Docker image's default user is a superuser. So the very first version of this project had textbook-correct RLS policies that did nothing at all, and every test that should have proven isolation passed by accident, because the role running them could see everything regardless.

The fix is `sql/000_app_role.sql`: a dedicated `tenant_vault_app` role, `NOSUPERUSER NOBYPASSRLS`, that owns no tables and has exactly the `SELECT`/`INSERT`/`UPDATE`/`DELETE` grants it needs (`sql/002_grants.sql`). Migrations run as the schema owner; the application never does. `tests/test_tenant_isolation.py::test_raw_query_with_no_where_clause_still_only_sees_its_own_org` is the test that would have caught this from day one, had it been run against the right role — it issues a bare `SELECT * FROM records` with zero filtering, inside one org's transaction context, and asserts the other org's row is not there.

**The same bug, again, on managed Postgres.** On Neon, the default owner role (`neondb_owner`) is not a superuser but *does* have `BYPASSRLS`. Point `DATABASE_URL` at the connection string Neon hands you by default and every policy above is silently off. So the app now refuses to start if its own role is a superuser or has `BYPASSRLS` (`assert_role_cannot_bypass_rls` in `app/db/session.py`, run at startup, tested in `tests/test_startup_guard.py`). The deployed API runs as `tenant_vault_app`, whose password comes from `APP_DB_PASSWORD` at migration time rather than from the repo.

**Login without an RLS bypass.** Logging in needs to find a user by email before an org context exists — the same problem as the bug above, in miniature. The obvious fix, a global "look up any user by email" query, is exactly the kind of query that has to run outside RLS and would be the one deliberate hole in an otherwise absolute boundary. Instead, login and signup take an organization slug (`POST /auth/login {"organization_slug", "email", "password"}`), the same shape as GitHub, Slack, or Linear's "which workspace" step. The only query in this codebase against a non-RLS-protected table is resolving that slug to an org id; every subsequent query, including the user lookup, runs inside that org's transaction context.

## What else is here

- **RBAC** (`app/auth/dependencies.py`): three roles (viewer < member < admin), gating specific routes independently of tenant isolation. A 403 (wrong role) and a 404 (RLS hid the row) are deliberately different outcomes — see the comment in `app/records/routes.py`.
- **Audit log**: every mutation writes to `audit_log` in the same transaction as the change, so a rollback takes the audit record with it — there's no path where a mutation succeeds unaudited.
- **Signed webhooks** (`app/webhooks/routes.py`): per-org endpoint (`/webhooks/{org_slug}/inbound`), HMAC-SHA256 verified, idempotent on the sender's event id.
- **Background jobs** (`app/jobs/`): a Postgres-backed queue, claimed with `FOR UPDATE SKIP LOCKED`. The worker loops per-organization rather than querying jobs across every tenant at once — the same reason login needed a slug, there is no query in this codebase that reads a tenant table without an org context, including the worker's.
- **AI feature** (`app/ai/summarize.py`): every created record is queued for a summary rather than summarized inline, so record creation never waits on an LLM call. The summarizer is a `Protocol`; tests inject a fake, so the suite runs deterministically with no API key.

## Running it

```bash
docker compose up -d --wait                      # Postgres on :5435
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python -m app.db.migrate                         # creates tenant_vault_app + schema + policies
uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev                                       # :3000, talks to the API on :8000
```

Or the whole stack in Docker: `docker compose -f docker-compose.full.yml up --build`.

## Tests

```bash
cd backend && pytest -v      # 22 tests against real Postgres, including the isolation suite above
cd frontend && npm test      # 8 tests
```

CI runs both, plus `ruff`, `mypy`, `eslint`, `tsc`, and a production `next build`, on every push.

## Layout

```
backend/
  app/db/            engine + tenant_session (the set_config wiring), migration runner
  app/auth/           JWT issuance, RBAC dependency, signup/login (slug-based, see above)
  app/records/        the tenant-scoped CRUD resource
  app/webhooks/       signed, idempotent, per-org inbound webhook
  app/jobs/           Postgres queue + per-org worker loop
  app/ai/             summarization behind a Protocol, swappable for a real LLM client
  sql/                000_app_role, 001_schema (RLS policies), 002_grants
  tests/              test_tenant_isolation.py is the one that matters most
frontend/
  app/login, app/records   Next.js App Router pages
  lib/api.ts               typed fetch client
```
