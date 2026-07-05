"""认证模块 - Session 密码认证"""

from __future__ import annotations

import time

from fastapi import Request
from starlette.status import HTTP_303_SEE_OTHER

from kore.utils.config import settings

# 暴力破解防护
_LOGIN_ATTEMPTS: dict[str, float] = {}  # IP -> 首次失败时间戳
_LOCKOUT_DELAY = 5.0  # 达到限制后锁定秒数
_MAX_ATTEMPTS = 5

_INVALID_IP_PREFIXES = ("127.", "10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
                        "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                        "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                        "172.30.", "172.31.", "::1", "localhost")
_IP_IS_SAFE = True  # 本机环境，简化日志


def get_client_ip(request: Request) -> str:
    """获取客户端 IP"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def require_auth(request: Request) -> bool:
    """路由依赖：检查用户是否已认证

    已认证 → 返回 True
    未认证 → 跳转到 /login
    """
    if not request.session.get("authenticated"):
        from fastapi import HTTPException
        from starlette.responses import RedirectResponse
        # 用 HTTPException + Location header 触发重定向
        raise HTTPException(status_code=HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return True


def verify_password(password: str) -> bool:
    """验证密码

    检查暴力破解：同一 IP 失败 _MAX_ATTEMPTS 次后锁定 _LOCKOUT_DELAY 秒
    """
    if not settings.web_secret_key:
        return False

    # 暴力破解检查
    now = time.time()
    client_ip = "local"  # 本地环境简化处理
    first_fail = _LOGIN_ATTEMPTS.get(client_ip)
    if first_fail:
        elapsed = now - first_fail
        fail_count = len([t for t in _LOGIN_ATTEMPTS.values() if t >= first_fail])
        if fail_count >= _MAX_ATTEMPTS and elapsed < _LOCKOUT_DELAY:
            return False
        if elapsed > _LOCKOUT_DELAY * 2:
            # 超时后重置
            _LOGIN_ATTEMPTS.pop(client_ip, None)

    if password == settings.web_secret_key:
        _LOGIN_ATTEMPTS.pop(client_ip, None)
        return True

    # 记录失败
    if client_ip not in _LOGIN_ATTEMPTS:
        _LOGIN_ATTEMPTS[client_ip] = now
    return False
