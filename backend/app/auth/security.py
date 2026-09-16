from __future__ import annotations

import time
from uuid import UUID

import bcrypt
import jwt

from ..settings import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))


class AuthenticatedUser:
    def __init__(self, user_id: UUID, org_id: UUID, email: str, role: str):
        self.user_id = user_id
        self.org_id = org_id
        self.email = email
        self.role = role


def issue_token(user_id: UUID, org_id: UUID, email: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + settings.jwt_ttl_seconds,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


class TokenError(Exception):
    pass


def decode_token(token: str) -> AuthenticatedUser:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    return AuthenticatedUser(
        user_id=UUID(payload["sub"]),
        org_id=UUID(payload["org_id"]),
        email=payload["email"],
        role=payload["role"],
    )
