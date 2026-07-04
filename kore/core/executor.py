"""任务执行器 - 任务类型注册和分发"""

from __future__ import annotations

import json
from typing import Any

from kore.tasks.base import BaseTask, TaskResult
from kore.tasks.shell import ShellTask
from kore.tasks.python_task import PythonTask
from kore.tasks.http import HTTPTask
from kore.storage.models import Task, TaskType
from kore.utils.logger import get_logger

logger = get_logger("executor")

# 任务类型注册表
_task_registry: dict[TaskType, type[BaseTask]] = {
    TaskType.SHELL: ShellTask,
    TaskType.PYTHON: PythonTask,
    TaskType.HTTP: HTTPTask,
}


def register_task_type(task_type: TaskType, handler: type[BaseTask]) -> None:
    """注册自定义任务类型"""
    _task_registry[task_type] = handler
    logger.info("注册任务类型: %s -> %s", task_type, handler.__name__)


def get_task_handler(task_type: TaskType) -> type[BaseTask] | None:
    """获取任务处理器"""
    return _task_registry.get(task_type)


async def execute_task(task: Task, **extra_kwargs: Any) -> TaskResult:
    """执行任务

    Args:
        task: 任务数据库对象
        extra_kwargs: 执行时的额外参数

    Returns:
        执行结果
    """
    handler_cls = get_task_handler(task.task_type)
    if not handler_cls:
        logger.error("不支持的任务类型: %s", task.task_type)
        return TaskResult(
            success=False,
            error_message=f"不支持的任务类型: {task.task_type}",
        )

    try:
        config = json.loads(task.config) if isinstance(task.config, str) else task.config
    except json.JSONDecodeError:
        config = {}

    handler = handler_cls(config)
    kwargs = {**config, **extra_kwargs}
    kwargs["timeout"] = kwargs.get("timeout", task.timeout or 300)

    return await handler.execute(**kwargs)
