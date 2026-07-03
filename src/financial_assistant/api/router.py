"""API router aggregator — mounts the JSON API under ``/api``.

The sub-routers declare paths relative to ``/api`` (e.g. ``/auth/login``);
``create_app`` includes this aggregator with ``prefix="/api"`` so the final
paths are ``/api/auth/...``, ``/api/dashboard/...`` and ``/api/transactions``.
"""

from fastapi import APIRouter

from financial_assistant.api.auth_router import router as auth_router
from financial_assistant.api.dashboard_router import router as dashboard_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(dashboard_router)
