"""HTTP 请求任务 — SSRF 防护加固版"""

from __future__ import annotations

import ipaddress
import json
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from kore.tasks.base import BaseTask, TaskResult


def _is_private_ip(host: str) -> bool:
    """检查主机名解析后的 IP 是否属于内网/回环地址

    支持 IPv4 和 IPv6，解决 DNS 重绑定攻击问题。
    """
    # 先检查 hostname 本身是否是内网前缀（快速路径）
    _private_prefixes = (
        "127.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
        "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
        "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
        "172.30.", "172.31.", "192.168.", "0.",
        "169.254.",
        "::1", "::", "0:0:0:0:0:0:0:1",
        "fe80:", "fc00:", "fd00:",  # IPv6 链路本地 + 唯一本地
    )
    _exact_hosts = {"localhost", "localhost.localdomain"}

    host_lower = host.lower().strip()
    if host_lower in _exact_hosts:
        return True
    for prefix in _private_prefixes:
        if host_lower.startswith(prefix):
            return True

    # DNS 解析后检查所有解析到的 IP
    try:
        addrs = socket.getaddrinfo(host, 80, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        for addr in addrs:
            ip_str = addr[4][0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
                return True
    except (socket.gaierror, OSError, ValueError):
        pass  # DNS 解析失败，让 httpx 层处理

    return False


def _validate_url(url: str) -> None:
    """验证 URL 目标地址，禁止请求内网/回环地址（SSRF 防护）

    Args:
        url: 要验证的 URL
    Raises:
        ValueError: 如果 URL 目标被禁止
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # 仅允许 http/https 协议
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不支持的协议: {parsed.scheme}")

    # IP 级校验（含 DNS 解析）
    if _is_private_ip(hostname):
        raise ValueError(f"禁止请求内网/回环地址: {hostname}")


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

        # SSRF 防护校验（首次）
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

        # 重定向追踪的 SSRF 校验
        async def _check_redirect(request: httpx.Request) -> None:
            """每次重定向时校验目标 URL"""
            redirect_url = str(request.url)
            try:
                _validate_url(redirect_url)
            except ValueError as e:
                raise httpx.InvalidURL(str(e))

        try:
            async with httpx.AsyncClient(
                verify=verify_ssl,
                follow_redirects=follow_redirects,
                timeout=httpx.Timeout(timeout),
                event_hooks={"request": [_check_redirect]} if follow_redirects else None,
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

        except httpx.InvalidURL as e:
            return TaskResult(
                success=False,
                stderr=f"重定向目标地址被拒绝: {e}",
                error_message=str(e),
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
