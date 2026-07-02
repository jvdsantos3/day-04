"""Auth service — password hashing (T5, AUTH-01).

SPEC_DEVIATION: design.md lists ``passlib[bcrypt]`` as the hashing dependency.
Reason: passlib 1.7.4 fails to initialize its bcrypt backend against the
installed bcrypt 5.0.0 (backend detection raises "password cannot be longer
than 72 bytes"). We call the ``bcrypt`` library directly — the same backend
passlib wraps — which satisfies AUTH-01's "senha hasheada (bcrypt)".
"""

import bcrypt


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt (fresh salt per call)."""
    hashed = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if ``plain`` matches the bcrypt ``hashed`` value."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
