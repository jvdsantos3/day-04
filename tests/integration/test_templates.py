"""Integration tests for the base Jinja2 layout + static CSS (T26, WEB-01).

``base.html`` is the shared shell that T27/T28/T29 extend for the dashboard
and chat pages — those pages don't exist yet, so this test mounts a
throwaway probe route (same pattern as ``test_auth.py``'s ``api_client``
fixture) to render the layout directly through a TestClient.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from financial_assistant.main import create_app

pytestmark = pytest.mark.integration

_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "financial_assistant"
    / "web"
    / "templates"
)

PROBE_PATH = "/_probe/base-template"


@pytest.fixture
def client():
    app = create_app()
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    @app.get(PROBE_PATH)
    def _probe_base_template(request: Request):
        return templates.TemplateResponse(
            request, "base.html", {"user": SimpleNamespace(name="Ana")}
        )

    with TestClient(app) as test_client:
        yield test_client


def test_base_template_renders_layout_with_nav(client):
    resp = client.get(PROBE_PATH)

    assert resp.status_code == 200
    body = resp.text
    # Design.md dashboard header: "Olá, {nome} [Chat] [Logout]".
    assert "Olá, Ana" in body
    assert 'href="/chat"' in body
    assert 'action="/logout"' in body


def test_base_template_includes_htmx_script(client):
    resp = client.get(PROBE_PATH)

    # AD-001 / design.md: HTMX drives dashboard filters without a full reload.
    assert "htmx.org" in resp.text


def test_static_css_is_served(client):
    resp = client.get("/static/css/style.css")

    assert resp.status_code == 200
    # Minimal CSS for category cards, progress bars and the transaction table.
    assert ".category-card" in resp.text
    assert ".progress-bar" in resp.text
    assert "table" in resp.text
