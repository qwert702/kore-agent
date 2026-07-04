"""HTTP 请求任务"""

from __future__ import annotations

import json
from typing import Any

import httpx

from kore.tasks.base import BaseTask, TaskResult


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
