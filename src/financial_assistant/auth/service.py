"""Auth service — password hashing (T5, AUTH-01).

SPEC_DEVIATION: design.md lists ``passlib[bcrypt]`` as the hashing dependency.
Reason: passlib 1.7.4 fails to initialize its bcrypt backend against the
installed bcrypt 5.0.0 (backend detection raises "password cannot be longer
than 72 bytes"). We call the ``bcrypt`` library directly — the same backend
passlib wraps — which satisfies AUTH-01's "senha hasheada (bcrypt)".
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from financial_assistant.config import get_settings

_JWT_ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt (fresh salt per call)."""
    hashed = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if ``plain`` matches the bcrypt ``hashed`` value."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str) -> str:
    """Sign a JWT (HS256) whose ``sub`` is the authenticated user's id.

    Expiry is taken from ``jwt_expire_minutes`` in settings (AUTH-03).
    """
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    claims = {"sub": subject, "exp": expire}
    return jwt.encode(claims, settings.jwt_secret, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Return the ``sub`` claim if ``token`` is a valid, unexpired JWT, else None."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_JWT_ALGORITHM])
    except JWTError:
        return None
    return payload.get("sub")
