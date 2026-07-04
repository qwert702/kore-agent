"""工具模块测试"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from kore.utils.config import Settings
from kore.utils.safe_path import safe_resolve, PathTraversalError, is_safe_filename


class TestConfig:
    def test_default_values(self) -> None:
        """测试默认配置加载"""
        s = Settings()
        assert s.log_level == "INFO"
        assert s.task_default_timeout == 300

    def test_env_override(self, monkeypatch) -> None:
        """测试环境变量覆盖"""
        monkeypatch.setenv("AGENT_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("AGENT_TASK_DEFAULT_TIMEOUT", "600")
        s = Settings()
        assert s.log_level == "DEBUG"
        assert s.task_default_timeout == 600


class TestSafePath:
    def test_safe_resolve_in_base(self, tmp_path: Path) -> None:
        """测试在基目录内的路径解析"""
        target = tmp_path / "subdir" / "test.txt"
        target.parent.mkdir(parents=True)
        target.write_text("test")
        # 用绝对路径测试
        resolved = safe_resolve(str(target), str(tmp_path))
        assert resolved == target.resolve()

    def test_path_traversal_detected(self, tmp_path: Path) -> None:
        """测试目录遍历攻击检测"""
        with pytest.raises(PathTraversalError):
            safe_resolve("../outside.txt", str(tmp_path))

    def test_safe_filename_valid(self) -> None:
        assert is_safe_filename("normal.txt")
        assert is_safe_filename("hello_world.py")

    def test_safe_filename_invalid(self) -> None:
        assert not is_safe_filename("../evil.txt")
        assert not is_safe_filename("a/b.txt")
        assert not is_safe_filename("")


class TestLogger:
    def test_logger_setup(self) -> None:
        """测试日志器初始化"""
        from kore.utils.logger import get_logger
        log = get_logger("test")
        assert log.name == "agent.test"
        log.info("test message")  # 不应抛出异常

    def test_json_format(self) -> None:
        """测试 JSON 日志格式"""
        from kore.utils.logger import JSONFormatter
        import logging

        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="hello",
            args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "hello"


class TestRetry:
    def test_success_first_attempt(self) -> None:
        """测试首次成功无需重试"""
        from kore.utils.retry import retry

        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def func() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = func()
        assert result == "ok"
        assert call_count == 1

    def test_retry_then_success(self) -> None:
        """测试重试后成功"""
        from kore.utils.retry import retry, RetryError

        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def func() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        result = func()
        assert result == "ok"
        assert call_count == 3

    def test_all_attempts_fail(self) -> None:
        """测试所有重试耗尽后抛出异常"""
        from kore.utils.retry import retry, RetryError

        @retry(max_attempts=2, delay=0.01)
        def func() -> str:
            raise ValueError("always fail")

        with pytest.raises(RetryError):
            func()
