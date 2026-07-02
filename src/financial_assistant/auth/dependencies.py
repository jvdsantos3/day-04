"""Auth dependency — resolve the current user from the JWT session cookie (T7).

Realises AUTH-05: an unauthenticated request to a protected route is redirected
to ``/login?next=<path>`` (raised as a 302 so route handlers never run without a
user). T8 builds on this for repository-level user isolation (AUTH-06).
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


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Return the authenticated :class:`User` or redirect to /login (AUTH-05)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise _redirect_to_login(request)

    subject = decode_access_token(token)
    if subject is None:
        raise _redirect_to_login(request)

    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        raise _redirect_to_login(request)

    user = db.get(User, user_id)
    if user is None:
        raise _redirect_to_login(request)

    return user
