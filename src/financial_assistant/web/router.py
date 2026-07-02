"""Web router — authenticated pages.

STUB (T7): a minimal protected ``/dashboard`` so login-redirect and the
route-protection test (AUTH-05) are coherent. T27 replaces this with the real
dashboard (transaction table + category bars). The ``get_current_user``
dependency enforces authentication; unauthenticated requests are redirected to
/login before this handler runs.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from financial_assistant.auth.dependencies import get_current_user
from financial_assistant.domain.models import User

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(user: User = Depends(get_current_user)) -> HTMLResponse:
    # Placeholder body; the real dashboard is built in T27.
    return HTMLResponse(f"<h1>Olá, {user.name}</h1>")
