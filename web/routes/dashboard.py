"""仪表盘路由"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from kore.core.scheduler import scheduler
from kore.storage.db import get_sync_session
from kore.storage.models import TaskRun
from kore.storage.repository import TaskRepository
from kore.utils.config import settings
from sqlalchemy import select
from web.auth import require_auth

router = APIRouter()

# 使用绝对路径确保不受 CWD 影响
_TEMPLATES_DIR = str(Path(__file__).resolve().parent.parent / "templates").replace("\\", "/")
TEMPLATES = Jinja2Templates(directory=_TEMPLATES_DIR)


def _task_dict(t: object) -> dict:
    """ORM 对象转 dict"""
    return {
        "id": t.id,
        "name": t.name,
        "task_type": t.task_type.value if hasattr(t.task_type, "value") else t.task_type,
        "status": t.status.value if hasattr(t.status, "value") else t.status,
        "schedule_expr": t.schedule_expr or "",
        "config": t.config,
        "description": t.description,
        "timeout": t.timeout,
        "tags": t.tags,
        "created_at": str(t.created_at) if t.created_at else "",
    }


def _run_dict(r: object) -> dict:
    """Run ORM 对象转 dict"""
    return {
        "id": r.id,
        "task_id": r.task_id,
        "task_name": getattr(r.task, "name", f"#{r.task_id}") if hasattr(r, "task") else f"#{r.task_id}",
        "status": r.status.value if hasattr(r.status, "value") else r.status,
        "trigger": r.trigger,
        "started_at": str(r.started_at) if r.started_at else "",
        "finished_at": str(r.finished_at) if r.finished_at else "",
        "duration_ms": r.duration_ms,
        "exit_code": r.exit_code,
        "stdout": r.stdout or "",
        "stderr": r.stderr or "",
        "error_message": r.error_message or "",
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    _: bool = Depends(require_auth),
) -> HTMLResponse:
    """仪表盘首页"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        tasks = repo.list_tasks(limit=1000)
        all_tasks = [_task_dict(t) for t in tasks]

        # 统计
        total = len(all_tasks)
        active = sum(1 for t in all_tasks if t["status"] == "active")
        paused = sum(1 for t in all_tasks if t["status"] == "paused")

        # 今日执行
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        runs_stmt = (
            select(TaskRun)
            .where(TaskRun.started_at >= today_start)
            .order_by(TaskRun.started_at.desc())
            .limit(50)
        )
        recent_runs_raw = list(session.scalars(runs_stmt).all())
        recent_runs = [_run_dict(r) for r in recent_runs_raw]

    # 调度器状态
    try:
        scheduler_running = scheduler.is_running
        scheduled_jobs = len(scheduler.list_jobs()) if scheduler_running else 0
    except Exception:
        scheduler_running = False
        scheduled_jobs = 0

    return TEMPLATES.TemplateResponse(request, "dashboard.html", {
        "stats": {
            "total": total,
            "total": total,
            "active": active,
            "paused": paused,
            "today_runs": len(recent_runs),
        },
        "recent_runs": recent_runs[:10],
        "scheduler_running": scheduler_running,
        "scheduled_jobs": scheduled_jobs,
        "daemon_port": settings.daemon_port,
    })


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """登录页"""
    if request.session.get("authenticated"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/", status_code=303)
    return TEMPLATES.TemplateResponse(request, "login.html", {"error": ""})


@router.post("/login")
async def login_submit(request: Request) -> HTMLResponse:
    """登录提交"""
    form = await request.form()
    password = form.get("password", "")

    from web.auth import verify_password
    if verify_password(password):
        request.session["authenticated"] = True
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/", status_code=303)

    from starlette.responses import RedirectResponse
    return TEMPLATES.TemplateResponse(request, "login.html", {"error": ""}, status_code=401)


@router.get("/logout")
async def logout(request: Request):
    """退出登录"""
    request.session.clear()
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/login", status_code=303)
