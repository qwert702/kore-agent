"""API 路由注册（v1）"""

from __future__ import annotations

from fastapi import FastAPI


def register_api_routes(app: FastAPI) -> None:
    """注册所有 API v1 路由"""
    from web.api.v1_tasks import router as tasks_router
    from web.api.v1_runs import router as runs_router
    from web.api.v1_stats import router as stats_router

    app.include_router(tasks_router, prefix="/api/v1")
    app.include_router(runs_router, prefix="/api/v1")
    app.include_router(stats_router, prefix="/api/v1")
