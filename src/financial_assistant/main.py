"""FastAPI application factory.

Wires the routers into an app instance. Kept minimal — routers are added as
their tasks land (auth first, then web/chat). Tests build their own app via
``create_app()`` and override the DB dependency for isolation.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from financial_assistant.api.router import router as api_router
from financial_assistant.auth.router import router as auth_router
from financial_assistant.chat.router import router as chat_router
from financial_assistant.web.router import router as web_router

_STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(title="Assistente Financeiro")
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/login", status_code=302)

    app.include_router(auth_router)
    app.include_router(web_router)
    app.include_router(chat_router)
    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
