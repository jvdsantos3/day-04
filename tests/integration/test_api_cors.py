"""CORS configuration for the React SPA dev origin (T5, CORS-01).

The Vite dev server (http://localhost:5173) calls the API cross-origin and
must be allowed to send the session cookie. These tests assert the app echoes
the exact allowed origin and credentials flag on both a preflight (OPTIONS)
and a simple request, and that the api_router is reachable at its /api path.
"""

import pytest
from fastapi.testclient import TestClient

from financial_assistant.main import create_app

pytestmark = pytest.mark.integration

ORIGIN = "http://localhost:5173"


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_cors_preflight_allows_frontend_origin(client):
    resp = client.options(
        "/api/auth/login",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
        },
    )

    # CORS-01: preflight echoes the exact allowed origin + credentials flag.
    assert resp.headers.get("access-control-allow-origin") == ORIGIN
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_simple_request_includes_credentials_headers(client):
    # A GET to a real /api path (401 without a cookie) still carries CORS headers,
    # confirming the api_router is mounted under /api and the middleware applies.
    resp = client.get("/api/auth/me", headers={"Origin": ORIGIN})

    assert resp.status_code == 401
    assert resp.headers.get("access-control-allow-origin") == ORIGIN
    assert resp.headers.get("access-control-allow-credentials") == "true"
