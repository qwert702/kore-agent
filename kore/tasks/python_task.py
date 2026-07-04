"""Python 脚本执行任务"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from kore.tasks.base import BaseTask, TaskResult
from kore.utils.safe_path import safe_resolve, PathTraversalError


class PythonTask(BaseTask):
    """执行 Python 脚本"""

    @property
    def name(self) -> str:
        return "python"

    async def execute(self, **kwargs: Any) -> TaskResult:
        script = self.config.get("script", kwargs.get("script", ""))
        script_path = self.config.get("script_path", kwargs.get("script_path", ""))
        timeout = self.config.get("timeout", kwargs.get("timeout", 300))

        # 三选一：内联脚本 / 脚本文件路径 / 模块名
        if script:
            # 直接执行内联代码
            return await self._run_inline(script, timeout)
        elif script_path:
            return await self._run_file(script_path, timeout)
        else:
            return TaskResult(
                success=False,
                stderr="未指定 Python 脚本内容或路径",
                error_message="script 和 script_path 都为空",
            )

    async def _run_inline(self, code: str, timeout: int) -> TaskResult:
        """执行内联 Python 代码"""
        self.logger.info("执行内联 Python 代码 (%d chars)", len(code))

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        return await self._wait_process(proc, timeout)

    async def _run_file(self, script_path: str, timeout: int) -> TaskResult:
        """执行 Python 脚本文件"""
        try:
            resolved = safe_resolve(script_path)
        except PathTraversalError as e:
            return TaskResult(
                success=False,
                stderr=str(e),
                error_message="路径安全检查失败",
                exit_code=-1,
            )

        if not resolved.exists():
            return TaskResult(
                success=False,
                stderr=f"脚本文件不存在: {resolved}",
                error_message="文件未找到",
                exit_code=-1,
            )

        self.logger.info("执行 Python 文件: %s", resolved)

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(resolved),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        return await self._wait_process(proc, timeout)

    async def _wait_process(self, proc: asyncio.subprocess.Process, timeout: int) -> TaskResult:
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return TaskResult(
                success=False,
                stderr=f"Python 脚本执行超时（{timeout}秒）",
                error_message=f"Timeout after {timeout}s",
                exit_code=-1,
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        exit_code = proc.returncode or 0
        success = exit_code == 0

        return TaskResult(
            success=success,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
        )
