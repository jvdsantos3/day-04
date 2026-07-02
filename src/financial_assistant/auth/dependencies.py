"""Auth dependency — resolve the current user from the JWT session cookie.

Two entry points share the same token → user resolution but differ in how they
reject an unauthenticated request:

- :func:`get_current_user` (web routes) redirects to ``/login?next=<path>``
  (302), realising AUTH-05 so browser navigations land on the login form.
- :func:`get_current_user_api` (API routes) raises ``401 Unauthorized`` so
  programmatic callers get a status code instead of an HTML redirect.

Both make the authenticated ``user_id`` the mandatory scoping key for every
downstream data access (AUTH-06).
"""

import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from financial_assistant.auth.service import decode_access_token
from financial_assistant.db.session import get_db
from financial_assistant.domain.models import User

SESSION_COOKIE_NAME = "access_token"


def _redirect_to_login(request: Request) -> HTTPException:
    """Build a 302-to-login exception preserving the originally requested path."""
    next_path = request.url.path
    return HTTPException(
        status_code=status.HTTP_302_FOUND,
        detail="Not authenticated",
        headers={"Location": f"/login?next={next_path}"},
    )


def _resolve_user(request: Request, db: Session) -> User | None:
    """Resolve the session cookie to a :class:`User`, or ``None`` if invalid.

    Returns ``None`` for a missing, malformed, or expired token, or when the
    token's subject no longer maps to a user. Callers decide how to reject.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    subject = decode_access_token(token)
    if subject is None:
        return None

    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        return None

    return db.get(User, user_id)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Return the authenticated :class:`User` or redirect to /login (AUTH-05).

    For browser-facing (web) routes: an unauthenticated request is redirected
    to the login form.
    """
    user = _resolve_user(request, db)
    if user is None:
        raise _redirect_to_login(request)
    return user


def get_current_user_api(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Return the authenticated :class:`User` or raise ``401`` (AUTH-06).

    For API routes: an unauthenticated request gets a ``401 Unauthorized`` status
    rather than an HTML redirect, so programmatic clients can react to it.
    """
    user = _resolve_user(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user
