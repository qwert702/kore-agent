"""API v1 - 统计数据"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from starlette.responses import JSONResponse

from kore.storage.db import get_sync_session
from kore.storage.models import RunStatus, TaskRun, TaskStatus
from kore.storage.repository import TaskRepository
from web.auth import require_api_token

router = APIRouter(tags=["stats"])


@router.get("/stats", dependencies=[Depends(require_api_token)])
async def api_stats() -> JSONResponse:
    """获取系统统计数据"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        tasks = repo.list_tasks(limit=5000)
        total = len(tasks)
        active = sum(1 for t in tasks if t.status == TaskStatus.ACTIVE)
        paused = sum(1 for t in tasks if t.status == TaskStatus.PAUSED)

        # 今日执行
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = session.scalar(
            select(func.count(TaskRun.id)).where(TaskRun.started_at >= today_start)
        ) or 0

        # 按状态统计
        success_count = session.scalar(
            select(func.count(TaskRun.id)).where(TaskRun.status == RunStatus.SUCCESS)
        ) or 0
        failed_count = session.scalar(
            select(func.count(TaskRun.id)).where(TaskRun.status == RunStatus.FAILED)
        ) or 0

    return JSONResponse({
        "tasks": {
            "total": total,
            "active": active,
            "paused": paused,
        },
        "runs": {
            "today": today_count,
            "success": success_count,
            "failed": failed_count,
        },
    })
