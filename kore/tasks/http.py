"""HTTP 请求任务"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import httpx

from kore.tasks.base import BaseTask, TaskResult


# 禁止请求的内网地址前缀列表（SSRF 防护）
_BLOCKED_HOST_PREFIXES = [
    "127.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
    "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
    "172.30.", "172.31.", "192.168.", "0.",
    "169.254.",  # 链路本地
    "::1", "::", "0:0:0:0:0:0:0:1",  # IPv6 回环
]

_BLOCKED_HOSTS_EXACT = [
    "localhost",
    "localhost.localdomain",
]


def _validate_url(url: str) -> None:
    """验证 URL 目标地址，禁止请求内网/回环地址（SSRF 防护）

    Args:
        url: 要验证的 URL
    Raises:
        ValueError: 如果 URL 目标被禁止
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # 精确匹配
    if hostname.lower() in _BLOCKED_HOSTS_EXACT:
        raise ValueError(f"禁止请求内网/回环地址: {hostname}")

    # 前缀匹配（IPv4 和 IPv6）
    for prefix in _BLOCKED_HOST_PREFIXES:
        if hostname.startswith(prefix):
            raise ValueError(f"禁止请求内网/回环地址: {hostname}")

    # 仅允许 http/https 协议
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不支持的协议: {parsed.scheme}")


class HTTPTask(BaseTask):
    """执行 HTTP 请求"""

    @property
    def name(self) -> str:
        return "http"

    async def execute(self, **kwargs: Any) -> TaskResult:
        url = self.config.get("url", kwargs.get("url", ""))
        method = self.config.get("method", kwargs.get("method", "GET")).upper()
        timeout = self.config.get("timeout", kwargs.get("timeout", 30))
        headers = self.config.get("headers", kwargs.get("headers", {}))
        params = self.config.get("params", kwargs.get("params", {}))
        body = self.config.get("body", kwargs.get("body"))
        follow_redirects = self.config.get("follow_redirects", True)
        verify_ssl = self.config.get("verify_ssl", True)

        if not url:
            return TaskResult(
                success=False,
                stderr="未指定 URL",
                error_message="url 参数为空",
            )

        self.logger.info("HTTP %s %s", method, url)

        # SSRF 防护校验
        try:
            _validate_url(url)
        except ValueError as e:
            return TaskResult(
                success=False,
                stderr=str(e),
                error_message=str(e),
            )

        valid_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        if method not in valid_methods:
            return TaskResult(
                success=False,
                stderr=f"不支持的 HTTP 方法: {method}",
                error_message=f"Invalid method: {method}",
            )

        try:
            async with httpx.AsyncClient(
                verify=verify_ssl,
                follow_redirects=follow_redirects,
                timeout=httpx.Timeout(timeout),
            ) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=body if method in ("POST", "PUT", "PATCH") and isinstance(body, dict) else None,
                    content=json.dumps(body) if body and not isinstance(body, dict) else None,
                )

                # 尝试解析 JSON 响应
                try:
                    data = response.json()
                except (json.JSONDecodeError, UnicodeDecodeError):
                    data = {"text": response.text[:2000]}

                success = 200 <= response.status_code < 300
                log_msg = f"HTTP {method} {url} -> {response.status_code}"
                if success:
                    self.logger.info(log_msg)
                else:
                    self.logger.warning(log_msg)

                return TaskResult(
                    success=success,
                    stdout=response.text[:5000],
                    stderr=f"HTTP {response.status_code}" if not success else "",
                    data={
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "body": data,
                    },
                )

        except httpx.TimeoutException:
            return TaskResult(
                success=False,
                stderr=f"HTTP 请求超时（{timeout}秒）",
                error_message=f"Timeout after {timeout}s",
            )
        except httpx.RequestError as e:
            return TaskResult(
                success=False,
                stderr=f"HTTP 请求失败: {e}",
                error_message=str(e),
            )
