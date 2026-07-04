"""任务类型基类和接口"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from kore.utils.logger import get_logger


@dataclass
class TaskResult:
    """任务执行结果"""

    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    error_message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "error_message": self.error_message,
            "data": self.data,
        }


class BaseTask(ABC):
    """所有任务类型的基类"""

    def __init__(self, config: dict[str, Any] | str | None = None) -> None:
        if isinstance(config, str):
            self.config = json.loads(config) if config else {}
        else:
            self.config = config or {}
        self.logger = get_logger(f"task.{self.name}")

    @property
    @abstractmethod
    def name(self) -> str:
        """任务类型名称"""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> TaskResult:
        """执行任务

        Args:
            kwargs: 执行时传入的附加参数（从任务配置合并）

        Returns:
            执行结果
        """
