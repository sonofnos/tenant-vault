from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from .security import AuthenticatedUser, TokenError, decode_token

# Roles are ordered least to most privileged; RANK lets `require_role` express
# "at least this role" without a hardcoded list of allowed roles per route.
RANK = {"viewer": 0, "member": 1, "admin": 2}


async def current_user(authorization: str = Header(default="")) -> AuthenticatedUser:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        return decode_token(authorization.removeprefix("Bearer ").strip())
    except TokenError:
        raise HTTPException(status_code=401, detail="invalid or expired token") from None


def require_role(minimum: str):
    """
    FastAPI dependency factory: `Depends(require_role("admin"))` on a route
    means "member and viewer get 403 here", independent of the org-isolation
    check, which RLS enforces regardless of role. Role answers "is this user
    allowed to do this kind of thing"; RLS answers "which rows exist for this
    user at all". A bug in one is not a bypass of the other.
    """

    async def _check(user: AuthenticatedUser = Depends(current_user)) -> AuthenticatedUser:
        if RANK.get(user.role, -1) < RANK.get(minimum, 99):
            raise HTTPException(status_code=403, detail=f"requires role '{minimum}' or higher")
        return user

    return _check
