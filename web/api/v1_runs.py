"""API v1 - 执行记录"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from starlette.responses import JSONResponse

from kore.storage.db import get_sync_session
from kore.storage.models import TaskRun
from web.auth import require_api_token

router = APIRouter(tags=["runs"])


def _run_json(r: object) -> dict[str, Any]:
    """TaskRun ORM → JSON dict"""
    return {
        "id": r.id,
        "task_id": r.task_id,
        "task_name": getattr(r.task, "name", f"#{r.task_id}") if hasattr(r, "task") and r.task else f"#{r.task_id}",
        "status": r.status.value if hasattr(r.status, "value") else r.status,
        "trigger": r.trigger,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "duration_ms": r.duration_ms,
        "exit_code": r.exit_code,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "error_message": r.error_message,
    }


@router.get("/runs", dependencies=[Depends(require_api_token)])
async def api_runs_list(
    task_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    """获取执行记录列表"""
    with get_sync_session() as session:
        stmt = select(TaskRun).options(joinedload(TaskRun.task))
        if task_id:
            stmt = stmt.where(TaskRun.task_id == task_id)
        stmt = stmt.order_by(TaskRun.started_at.desc()).offset(offset).limit(limit)
        runs = list(session.scalars(stmt).all())

    return JSONResponse({"runs": [_run_json(r) for r in runs], "total": len(runs)})


@router.get("/runs/{run_id}", dependencies=[Depends(require_api_token)])
async def api_run_get(run_id: int) -> JSONResponse:
    """获取执行记录详情"""
    with get_sync_session() as session:
        run = session.get(TaskRun, run_id)
        if not run:
            return JSONResponse({"detail": "Run not found"}, status_code=404)

    return JSONResponse({"run": _run_json(run)})
