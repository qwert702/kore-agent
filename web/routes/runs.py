"""执行记录路由"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.status import HTTP_303_SEE_OTHER

from kore.storage.db import get_sync_session
from kore.storage.models import TaskRun
from kore.storage.repository import TaskRepository
from web.auth import require_auth

router = APIRouter(prefix="/runs")
_TEMPLATES_DIR = str(Path(__file__).resolve().parent.parent / "templates").replace("\\", "/")
TEMPLATES = Jinja2Templates(directory=_TEMPLATES_DIR)


def _run_dict(r: object) -> dict:
    """Run ORM 对象转 dict"""
    return {
        "id": r.id,
        "task_id": r.task_id,
        "task_name": getattr(r.task, "name", f"#{r.task_id}") if hasattr(r, "task") and r.task else f"#{r.task_id}",
        "status": r.status.value if hasattr(r.status, "value") else r.status,
        "trigger": r.trigger,
        "started_at": str(r.started_at)[:19] if r.started_at else "",
        "finished_at": str(r.finished_at)[:19] if r.finished_at else "",
        "duration_ms": r.duration_ms,
        "exit_code": r.exit_code,
        "stdout": r.stdout or "",
        "stderr": r.stderr or "",
        "error_message": r.error_message or "",
    }


@router.get("", response_class=HTMLResponse)
async def runs_list(
    request: Request,
    _: bool = Depends(require_auth),
) -> HTMLResponse:
    """全部执行记录"""
    with get_sync_session() as session:
        stmt = (
            select(TaskRun)
            .order_by(TaskRun.started_at.desc())
            .limit(100)
        )
        runs_raw = list(session.scalars(stmt).all())
        runs = [_run_dict(r) for r in runs_raw]

    return TEMPLATES.TemplateResponse(request, "runs.html", {"runs": runs})


@router.get("/{run_id}", response_class=HTMLResponse)
async def run_detail(
    request: Request,
    run_id: int,
    _: bool = Depends(require_auth),
) -> HTMLResponse:
    """执行记录详情"""
    with get_sync_session() as session:
        run = session.get(TaskRun, run_id)
        if not run:
            return TEMPLATES.TemplateResponse(request, "404.html", {}, status_code=404)
        run_dict = _run_dict(run)

    return TEMPLATES.TemplateResponse(request, "run_detail.html", {"run": run_dict})
