"""任务类型执行测试"""

from __future__ import annotations

import pytest


class TestShellTask:
    """Shell 命令执行任务测试"""

    @pytest.mark.asyncio
    async def test_simple_command(self) -> None:
        """测试简单命令执行"""
        from kore.tasks.shell import ShellTask

        task = ShellTask({"command": "echo Hello World"})
        result = await task.execute()
        assert result.success
        assert "Hello World" in result.stdout
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_command_failure(self) -> None:
        """测试命令执行失败"""
        from kore.tasks.shell import ShellTask

        task = ShellTask({"command": "cmd /c exit 1"})
        result = await task.execute()
        assert not result.success
        assert result.exit_code != 0

    @pytest.mark.asyncio
    async def test_command_not_found(self) -> None:
        """测试命令不存在"""
        from kore.tasks.shell import ShellTask

        task = ShellTask({"command": "nonexistent_command_xyz123"})
        result = await task.execute()
        assert not result.success

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        """测试超时"""
        from kore.tasks.shell import ShellTask

        task = ShellTask({"command": "ping -n 10 127.0.0.1", "timeout": 1})
        result = await task.execute()
        assert not result.success


class TestHTTPTask:
    """HTTP 请求任务测试"""

    @pytest.mark.asyncio
    async def test_get_request(self) -> None:
        """测试 GET 请求（使用 GitHub API，可靠性更高）"""
        from kore.tasks.http import HTTPTask

        task = HTTPTask({
            "url": "https://api.github.com/zen",
            "method": "GET",
            "timeout": 15,
        })
        result = await task.execute()
        # GitHub API 可能返回 200 或 301（重定向），只要不是错误即可
        assert 200 <= result.data["status_code"] < 400, f"状态码: {result.data.get('status_code')}"

    @pytest.mark.asyncio
    async def test_invalid_url(self) -> None:
        """测试无效 URL"""
        from kore.tasks.http import HTTPTask

        task = HTTPTask({"url": "https://invalid.example.nonexist/test"})
        result = await task.execute()
        assert not result.success


class TestPythonTask:
    """Python 脚本执行任务测试"""

    @pytest.mark.asyncio
    async def test_inline_code(self) -> None:
        """测试内联代码执行"""
        from kore.tasks.python_task import PythonTask

        task = PythonTask({"script": "print('hello world')"})
        result = await task.execute()
        assert result.success
        assert "hello world" in result.stdout

    @pytest.mark.asyncio
    async def test_inline_code_failure(self) -> None:
        """测试代码执行错误"""
        from kore.tasks.python_task import PythonTask

        task = PythonTask({"script": "raise RuntimeError('fail')"})
        result = await task.execute()
        assert not result.success
        assert result.exit_code != 0
