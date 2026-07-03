"""FastAPI application factory.

Wires the routers into an app instance. Kept minimal — routers are added as
their tasks land (auth first, then web/chat). Tests build their own app via
``create_app()`` and override the DB dependency for isolation.

The React SPA (``frontend/dist``, built by ``npm run build``) is served by an
HTTP middleware fallback (DEPLOY-01), not a path route: a route registered
with a `/{full_path:path}` pattern would still be matched *before* any route
added to the app after ``create_app()`` returns (e.g. a test that mounts an
extra probe route on the built app), because Starlette matches routes in
registration order. The middleware runs the request through the normal
router first via ``call_next`` and only falls back to the SPA shell when
nothing else handled it (404) — so it is last by construction, regardless of
what other routes get added later, and explicit routers (including the old
Jinja2 HTML routes still present during this transition task) always win.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from financial_assistant.api.router import router as api_router
from financial_assistant.auth.router import router as auth_router
from financial_assistant.chat.router import router as chat_router
from financial_assistant.web.router import router as web_router

_STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"

# The Vite dev server origin the React SPA is served from in development
# (CORS-01). Cross-origin requests must carry the session cookie, so
# credentials are allowed for this exact origin.
_FRONTEND_DEV_ORIGIN = "http://localhost:5173"

# Repo-root-relative build output (``npm run build`` in ``frontend/``).
_DEFAULT_FRONTEND_DIST_DIR = (
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
)

_BUILD_MISSING_MESSAGE = (
    "Frontend build not found — run `npm run build` in `frontend/`."
)


def create_app(frontend_dist_dir: Path | str | None = None) -> FastAPI:
    """Build and return the FastAPI application.

    ``frontend_dist_dir`` overrides the SPA build directory (DEPLOY-01) —
    used by tests to exercise the "build missing" edge case without touching
    the real ``frontend/dist``.
    """
    dist_dir = Path(frontend_dist_dir) if frontend_dist_dir is not None else _DEFAULT_FRONTEND_DIST_DIR
    assets_dir = dist_dir / "assets"
    index_file = dist_dir / "index.html"

    app = FastAPI(title="Assistente Financeiro")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[_FRONTEND_DEV_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/login", status_code=302)

    app.include_router(auth_router)
    app.include_router(web_router)
    app.include_router(chat_router)
    app.include_router(api_router, prefix="/api")

    # Vite-generated, hashed JS/CSS bundles referenced by index.html as
    # /assets/index-XXXX.js. Mounted only when the directory exists so a
    # missing build doesn't crash app startup.
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="spa-assets")

    # SPA fallback (DEPLOY-01): only kicks in when no other route (present or
    # added later) handled the request with something other than 404.
    @app.middleware("http")
    async def spa_fallback(request: Request, call_next) -> Response:
        response = await call_next(request)
        if response.status_code != 404:
            return response

        if request.url.path.startswith("/api/"):
            # Never mask a real API 404 behind the SPA's index.html. Return
            # the 404 directly (raising here would escape the middleware
            # stack unhandled instead of reaching FastAPI's error handling).
            return response

        if index_file.is_file():
            return FileResponse(str(index_file))

        return HTMLResponse(content=_BUILD_MISSING_MESSAGE, status_code=503)

    return app


app = create_app()
