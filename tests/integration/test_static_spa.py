"""Integration tests for the SPA static mount + catch-all (T17, DEPLOY-01).

Covers the spec's edge case: "WHEN build React não existe em dev sem `npm run
dev` THEN FastAPI em prod SHALL retornar 503 com mensagem clara (não 404
silencioso)" plus the two happy-path contracts the fallback route promises —
arbitrary SPA routes render `index.html`, and unmatched `/api/*` paths keep
returning a real 404 instead of being masked by the SPA shell.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from financial_assistant.main import create_app

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DIST_DIR = _REPO_ROOT / "frontend" / "dist"


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_arbitrary_non_api_route_serves_the_spa_index(client):
    """GET /some-arbitrary-route (no physical file) -> 200 with the built index.html body.

    Uses a path that doesn't collide with the transitional Jinja2 HTML routes
    (/login, /register, /dashboard, /chat) still registered ahead of the
    catch-all during this task — those explicit routers must keep winning
    until T18 removes them, per DEPLOY-01's transition plan.
    """
    index_html = (_DIST_DIR / "index.html").read_text(encoding="utf-8")

    resp = client.get("/some-arbitrary-route")

    assert resp.status_code == 200
    assert '<div id="root">' in resp.text
    assert resp.text == index_html


def test_unmatched_api_route_returns_404_not_the_spa(client):
    """GET /api/rota-que-nao-existe -> 404, never the SPA's index.html."""
    resp = client.get("/api/rota-que-nao-existe")

    assert resp.status_code == 404
    assert "<div id=\"root\">" not in resp.text


def test_missing_build_returns_503_with_clear_message(tmp_path):
    """No frontend/dist/index.html -> 503 with a clear message, not a silent 404."""
    app = create_app(frontend_dist_dir=tmp_path)
    with TestClient(app) as client:
        resp = client.get("/some-arbitrary-route")

    assert resp.status_code == 503
    assert "npm run build" in resp.text
