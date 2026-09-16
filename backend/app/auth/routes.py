from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from ..db.session import tenant_session
from .schemas import LoginRequest, SignupRequest, SignupResponse, TokenResponse
from .security import hash_password, issue_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


async def _org_id_for_slug(slug: str):
    """
    The only query in this codebase allowed to run without a tenant context,
    because `organizations` carries no org_id to scope by and no sensitive
    data -- a name and a slug. Every other table is RLS-protected and every
    other query goes through tenant_session with a resolved org_id.
    """
    async with tenant_session(org_id=None) as session:
        result = await session.execute(text("SELECT id FROM organizations WHERE slug = :slug"), {"slug": slug})
        row = result.first()
    return row[0] if row else None


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(body: SignupRequest) -> SignupResponse:
    org_id = uuid4()
    user_id = uuid4()
    async with tenant_session(org_id=None) as session:
        existing_org = await session.execute(text("SELECT 1 FROM organizations WHERE slug = :slug"), {"slug": body.organization_slug})
        if existing_org.first() is not None:
            raise HTTPException(status_code=409, detail="organization slug already taken")
        await session.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": org_id, "name": body.organization_name, "slug": body.organization_slug},
        )

    # From here on, org_id is known, so every write happens inside a
    # tenant-scoped session even though this is a brand-new org with one user.
    async with tenant_session(org_id=org_id) as session:
        await session.execute(
            text("INSERT INTO users (id, org_id, email, password_hash, role_id) VALUES (:id, :org_id, :email, :hash, 1)"),
            {"id": user_id, "org_id": org_id, "email": body.email, "hash": hash_password(body.password)},
        )
    return SignupResponse(org_id=org_id, user_id=user_id)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    """
    Login resolves the organization by slug first -- a query against the one
    table that isn't RLS-protected -- and only then queries `users`, inside a
    session scoped to that org_id. There is no query anywhere in this service
    that looks up a user by email alone across every organization; that query
    would be the one deliberate crack in an otherwise absolute RLS boundary,
    and this schema does not have it.
    """
    org_id = await _org_id_for_slug(body.organization_slug)
    if org_id is None:
        raise HTTPException(status_code=401, detail="invalid credentials")

    async with tenant_session(org_id=org_id) as session:
        result = await session.execute(
            text("SELECT u.id, u.password_hash, r.name AS role FROM users u JOIN roles r ON r.id = u.role_id WHERE u.email = :email"),
            {"email": body.email},
        )
        row = result.mappings().first()

    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = issue_token(user_id=row["id"], org_id=org_id, email=body.email, role=row["role"])
    return TokenResponse(access_token=token)
