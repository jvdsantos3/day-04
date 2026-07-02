"""FastAPI application factory.

Wires the routers into an app instance. Kept minimal — routers are added as
their tasks land (auth first, then web/chat). Tests build their own app via
``create_app()`` and override the DB dependency for isolation.
"""

from fastapi import FastAPI

from financial_assistant.auth.router import router as auth_router
from financial_assistant.web.router import router as web_router


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(title="Assistente Financeiro")
    app.include_router(auth_router)
    app.include_router(web_router)
    return app


app = create_app()
