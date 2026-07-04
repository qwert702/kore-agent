"""Shell 命令执行任务"""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

from kore.tasks.base import BaseTask, TaskResult


class ShellTask(BaseTask):
    """执行 Shell 命令"""

    @property
    def name(self) -> str:
        return "shell"

    async def execute(self, **kwargs: Any) -> TaskResult:
        command = self.config.get("command", kwargs.get("command", ""))
        if not command:
            return TaskResult(
                success=False,
                stderr="未指定命令",
                error_message="command 参数为空",
            )

        timeout = self.config.get("timeout", kwargs.get("timeout", 300))
        cwd = self.config.get("cwd")
        env = self.config.get("env", {})

        # 安全：使用 shlex.split 而非 shell=True
        # 如果用户需要 shell 特性，可以通过 config.shell=true 显式启用
        use_shell = self.config.get("shell", False)

        self.logger.info("执行命令: %s (shell=%s, cwd=%s, timeout=%ds)", command, use_shell, cwd, timeout)

        try:
            if use_shell:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=env or None,
                )
            else:
                args = shlex.split(command, posix=False)
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=env or None,
                )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return TaskResult(
                    success=False,
                    stderr=f"命令执行超时（{timeout}秒）",
                    error_message=f"Timeout after {timeout}s",
                    exit_code=-1,
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode or 0

            success = exit_code == 0
            if success:
                self.logger.info("命令成功: exit=%d, stdout=%d chars", exit_code, len(stdout))
            else:
                self.logger.warning("命令失败: exit=%d, stderr=%d chars", exit_code, len(stderr))

            return TaskResult(
                success=success,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
            )

        except FileNotFoundError as e:
            return TaskResult(
                success=False,
                stderr=f"命令不存在: {e}",
                error_message=str(e),
                exit_code=-1,
            )
        except Exception as e:
            self.logger.error("命令执行异常: %s", e)
            return TaskResult(
                success=False,
                stderr=str(e),
                error_message=str(e),
                exit_code=-1,
            )
