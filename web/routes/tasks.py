"""任务管理页面路由"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_303_SEE_OTHER

from kore.core.executor import execute_task
from kore.storage.db import get_sync_session
from kore.storage.models import ScheduleType, TaskStatus, TaskType, RunStatus
from kore.storage.repository import TaskRepository
from web.auth import require_auth

router = APIRouter(prefix="/tasks")
_TEMPLATES_DIR = str(Path(__file__).resolve().parent.parent / "templates").replace("\\", "/")
TEMPLATES = Jinja2Templates(directory=_TEMPLATES_DIR)


def _task_dict(t: object) -> dict:
    """ORM 对象转 dict"""
    return {
        "id": t.id,
        "name": t.name,
        "task_type": t.task_type.value if hasattr(t.task_type, "value") else t.task_type,
        "status": t.status.value if hasattr(t.status, "value") else t.status,
        "schedule_type": t.schedule_type.value if t.schedule_type and hasattr(t.schedule_type, "value") else (t.schedule_type or ""),
        "schedule_expr": t.schedule_expr or "",
        "config": t.config,
        "description": t.description,
        "timeout": t.timeout,
        "tags": t.tags,
        "created_at": str(t.created_at) if t.created_at else "",
        "updated_at": str(t.updated_at) if t.updated_at else "",
    }


def _run_summary(r: object) -> dict:
    """Run 对象摘要（用于列表）"""
    return {
        "id": r.id,
        "task_id": r.task_id,
        "status": r.status.value if hasattr(r.status, "value") else r.status,
        "trigger": r.trigger,
        "started_at": str(r.started_at) if r.started_at else "",
        "duration_ms": r.duration_ms,
        "exit_code": r.exit_code,
    }


@router.get("", response_class=HTMLResponse)
async def task_list(
    request: Request,
    _: bool = Depends(require_auth),
) -> HTMLResponse:
    """任务列表页"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        tasks = repo.list_tasks(limit=100)
        result = []
        for t in tasks:
            d = _task_dict(t)
            # 最近执行时间
            if t.runs:
                d["last_run"] = str(t.runs[0].started_at)[:19] if t.runs[0].started_at else ""
            else:
                d["last_run"] = ""
            result.append(d)

    return TEMPLATES.TemplateResponse(request, "task_list.html", {
        "tasks": result,
    })


@router.get("/new", response_class=HTMLResponse)
async def task_new_form(
    request: Request,
    _: bool = Depends(require_auth),
) -> HTMLResponse:
    """新建任务表单页"""
    return TEMPLATES.TemplateResponse(request, "task_form.html", {"task": None})


@router.post("")
async def task_create(
    request: Request,
    _: bool = Depends(require_auth),
) -> HTMLResponse:
    """创建任务"""
    form = await request.form()
    name = form.get("name", "").strip()
    task_type_str = form.get("task_type", "")
    config_str = form.get("config", "{}")
    description = form.get("description", "")
    schedule_type_str = form.get("schedule_type", "") or None
    schedule_expr = form.get("schedule_expr", "") or None
    timeout = int(form.get("timeout", 300))
    tags = form.get("tags", "")

    if not name:
        return HTMLResponse("名称不能为空", status_code=400)
    if task_type_str not in ("shell", "http", "python"):
        return HTMLResponse(f"不支持的任务类型: {task_type_str}", status_code=400)

    st = None
    if schedule_type_str in ("cron", "interval", "date"):
        st = ScheduleType(schedule_type_str)

    try:
        config = json.loads(config_str) if isinstance(config_str, str) else {}
    except json.JSONDecodeError:
        return HTMLResponse("配置 JSON 格式错误", status_code=400)

    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.create_task(
            name=name,
            task_type=TaskType(task_type_str),
            config=config,
            description=description,
            schedule_type=st,
            schedule_expr=schedule_expr,
            timeout=timeout,
            tags=tags,
        )
        task_id = task.id

    return RedirectResponse(url=f"/tasks/{task_id}", status_code=HTTP_303_SEE_OTHER)


@router.get("/{task_id}", response_class=HTMLResponse)
async def task_detail(
    request: Request,
    task_id: int,
    _: bool = Depends(require_auth),
) -> HTMLResponse:
    """任务详情页"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.get_task(task_id)
        if not task:
            return TEMPLATES.TemplateResponse(request, "404.html", {}, status_code=404)

        runs = repo.get_task_runs(task_id, limit=50)
        task_dict = _task_dict(task)
        run_list = [_run_summary(r) for r in runs]

    return TEMPLATES.TemplateResponse(request, "task_detail.html", {"task": task_dict, "runs": run_list})


@router.get("/{task_id}/edit", response_class=HTMLResponse)
async def task_edit_form(
    request: Request,
    task_id: int,
    _: bool = Depends(require_auth),
) -> HTMLResponse:
    """编辑任务表单页"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.get_task(task_id)
        if not task:
            return TEMPLATES.TemplateResponse(request, "404.html", {}, status_code=404)
        task_dict = _task_dict(task)

    return TEMPLATES.TemplateResponse(request, "task_form.html", {"task": task_dict})


@router.post("/{task_id}")
async def task_update(
    request: Request,
    task_id: int,
    _: bool = Depends(require_auth),
) -> HTMLResponse:
    """更新任务"""
    form = await request.form()

    # 兼容 HTML 表单的 PUT（表单不支持 PUT 方法，用 _method 参数）
    method = form.get("_method", "POST")
    if method == "PUT":
        pass  # 走下面的更新逻辑

    name = form.get("name", "").strip()
    task_type_str = form.get("task_type", "")
    config_str = form.get("config", "{}")
    description = form.get("description", "")
    schedule_type_str = form.get("schedule_type", "") or None
    schedule_expr = form.get("schedule_expr", "") or None
    timeout = int(form.get("timeout", 300))
    tags = form.get("tags", "")

    try:
        config = json.loads(config_str) if isinstance(config_str, str) else {}
    except json.JSONDecodeError:
        return HTMLResponse("配置 JSON 格式错误", status_code=400)

    st = None
    if schedule_type_str in ("cron", "interval", "date"):
        st = ScheduleType(schedule_type_str)

    with get_sync_session() as session:
        repo = TaskRepository(session)
        updated = repo.update_task(
            task_id,
            name=name,
            task_type=TaskType(task_type_str),
            config=config,
            description=description,
            schedule_type=st,
            schedule_expr=schedule_expr,
            timeout=timeout,
            tags=tags,
        )
        if not updated:
            return TEMPLATES.TemplateResponse(request, "404.html", {}, status_code=404)

    return RedirectResponse(url=f"/tasks/{task_id}", status_code=HTTP_303_SEE_OTHER)


@router.post("/{task_id}/run")
async def task_run(
    request: Request,
    task_id: int,
    _: bool = Depends(require_auth),
) -> HTMLResponse:
    """触发任务执行"""
    import asyncio

    with get_sync_session() as session:
        repo = TaskRepository(session)
        task = repo.get_task(task_id)
        if not task:
            return TEMPLATES.TemplateResponse(request, "404.html", {}, status_code=404)

        run = repo.create_run(task_id=task_id, trigger="web")
        run_id = run.id

    # 后台执行
    async def _run_and_save():
        try:
            result = await execute_task(task)
            with get_sync_session() as session:
                repo2 = TaskRepository(session)
                repo2.update_run(
                    run_id,
                    status=RunStatus.SUCCESS if result.success else RunStatus.FAILED,
                    stdout=result.stdout or "",
                    stderr=result.stderr or "",
                    error_message=result.error_message or "",
                    exit_code=result.exit_code,
                )
        except Exception as e:
            with get_sync_session() as session:
                repo2 = TaskRepository(session)
                repo2.update_run(
                    run_id,
                    status=RunStatus.FAILED,
                    error_message=str(e),
                )

    asyncio.ensure_future(_run_and_save())
    return RedirectResponse(url=f"/runs/{run_id}", status_code=HTTP_303_SEE_OTHER)


@router.post("/{task_id}/pause")
async def task_pause(
    request: Request,
    task_id: int,
    _: bool = Depends(require_auth),
) -> HTMLResponse:
    """暂停任务"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        repo.set_task_status(task_id, TaskStatus.PAUSED)
    return RedirectResponse(url="/tasks", status_code=HTTP_303_SEE_OTHER)


@router.post("/{task_id}/resume")
async def task_resume(
    request: Request,
    task_id: int,
    _: bool = Depends(require_auth),
) -> HTMLResponse:
    """恢复任务"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        repo.set_task_status(task_id, TaskStatus.ACTIVE)
    return RedirectResponse(url="/tasks", status_code=HTTP_303_SEE_OTHER)


@router.post("/{task_id}/delete")
async def task_delete(
    request: Request,
    task_id: int,
    _: bool = Depends(require_auth),
) -> HTMLResponse:
    """删除任务"""
    with get_sync_session() as session:
        repo = TaskRepository(session)
        repo.delete_task(task_id)
    return RedirectResponse(url="/tasks", status_code=HTTP_303_SEE_OTHER)
