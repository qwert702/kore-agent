"""认证模块 - Session 密码认证 + API Token 认证"""

from __future__ import annotations

import hashlib
import secrets
import time

from fastapi import Request
from starlette.status import HTTP_303_SEE_OTHER

from kore.utils.config import settings

# ── 暴力破解防护 ──────────────────────────────────────
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}  # IP -> [失败时间戳列表]
_LOCKOUT_DELAY = 5.0   # 达到限制后锁定秒数
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 300  # 计数窗口：5 分钟内累计 _MAX_ATTEMPTS 次失败


def get_client_ip(request: Request) -> str:
    """获取客户端真实 IP"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def _hash_password(password: str) -> str:
    """密码哈希（SHA-256 + 随机 salt）"""
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{h}"


def _verify_hash(password: str, stored: str) -> bool:
    """验证密码哈希"""
    if ":" not in stored:
        # 明文比较（旧版兼容）
        return password == stored
    salt, h = stored.split(":", 1)
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest() == h


def is_rate_limited(ip: str) -> bool:
    """检查 IP 是否被限速"""
    now = time.time()
    attempts = _LOGIN_ATTEMPTS.get(ip, [])
    # 清理超出窗口的记录
    attempts = [t for t in attempts if now - t < _WINDOW_SECONDS]
    _LOGIN_ATTEMPTS[ip] = attempts

    if len(attempts) >= _MAX_ATTEMPTS:
        oldest = attempts[0]
        if now - oldest < _LOCKOUT_DELAY:
            return True
        # 锁定期已过，重置
        _LOGIN_ATTEMPTS[ip] = []
    return False


def record_attempt(ip: str) -> None:
    """记录一次失败尝试"""
    now = time.time()
    _LOGIN_ATTEMPTS.setdefault(ip, [])
    _LOGIN_ATTEMPTS[ip].append(now)


def require_auth(request: Request) -> bool:
    """路由依赖：检查用户是否已认证

    已认证 → 返回 True
    未认证 → 跳转到 /login
    """
    if not request.session.get("authenticated"):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return True


def get_admin_password() -> str:
    """获取管理密码（优先使用 web_admin_password，回退到 web_secret_key）"""
    if settings.web_admin_password:
        return settings.web_admin_password
    return settings.web_secret_key


def verify_password(password: str, client_ip: str = "unknown") -> bool:
    """验证管理密码（含暴力破解防护）

    Args:
        password: 用户输入的密码
        client_ip: 客户端 IP

    Returns:
        True 如果密码正确
    """
    admin_pw = get_admin_password()
    if not admin_pw:
        return False

    # 暴力破解检查
    if is_rate_limited(client_ip):
        return False

    # 密码验证
    if password == admin_pw:
        # 正确时清除该 IP 的失败记录
        _LOGIN_ATTEMPTS.pop(client_ip, None)
        return True

    # 记录失败
    record_attempt(client_ip)
    return False


# ── API Token 认证 ────────────────────────────────────

def _generate_api_token() -> str:
    """生成随机 API Token"""
    return secrets.token_urlsafe(32)


def get_api_token() -> str:
    """获取 API Token（从 settings 读取或自动生成）"""
    if hasattr(settings, "_api_token"):
        return settings._api_token  # type: ignore
    # 使用 secrets 模块生成固定 token（用 admin_password + 固定 salt 派生）
    admin_pw = get_admin_password()
    if not admin_pw:
        return ""
    h = hashlib.sha256(f"kore-api-token:{admin_pw}".encode()).hexdigest()
    token = h[:48]
    settings._api_token = token  # type: ignore
    return token


async def require_api_token(request: Request) -> bool:
    """API 路由依赖：检查 Bearer Token

    Authorization: Bearer <token>
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Missing or invalid API token")

    token = auth_header[len("Bearer "):]
    expected = get_api_token()
    if not expected or not secrets.compare_digest(token, expected):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Invalid API token")

    return True
