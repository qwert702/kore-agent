"""路由注册中心"""

from __future__ import annotations

from fastapi import FastAPI

from web.routes.dashboard import router as dashboard_router
from web.routes.tasks import router as tasks_router
from web.routes.runs import router as runs_router


def register_routes(app: FastAPI) -> None:
    """注册所有路由到应用"""
    app.include_router(dashboard_router)
    app.include_router(tasks_router)
    app.include_router(runs_router)
