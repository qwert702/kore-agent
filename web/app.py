"""Web 应用 - FastAPI 应用工厂"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from kore.core.scheduler import scheduler
from kore.storage.db import init_db
from kore.utils.config import settings
from kore.utils.logger import get_logger

logger = get_logger("web")

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期管理"""
    # startup
    logger.info("Web 服务启动中...")
    init_db()
    logger.info("数据库初始化完成")

    # 注册链式触发和通知处理器
    try:
        from kore.core.trigger import register_trigger_handlers
        register_trigger_handlers()
    except Exception as e:
        logger.warning("链式触发引擎初始化失败: %s", e)
    try:
        from kore.core.notifier import register_notify_handlers
        register_notify_handlers()
    except Exception as e:
        logger.warning("通知系统初始化失败: %s", e)

    try:
        await scheduler.start()
        logger.info("调度器已启动")
    except Exception as e:
        logger.warning("调度器启动失败（可继续运行）: %s", e)
    yield
    # shutdown
    try:
        await scheduler.stop()
        logger.info("调度器已停止")
    except Exception:
        pass
    logger.info("Web 服务已关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    if not settings.web_secret_key:
        raise RuntimeError(
            "必须设置 AGENT_WEB_SECRET_KEY 环境变量才能启动 Web 服务"
        )

    app = FastAPI(
        title="Kore Dashboard",
        description="kore 自动化任务编排引擎 - Web 管理界面",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Session 中间件（签名 Cookie）
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.web_secret_key,
        max_age=86400,  # 24 小时
        same_site="lax",
        https_only=False,  # 本地开发环境允许 HTTP
    )

    # 静态文件
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # 注册路由
    from web.routes import register_routes
    register_routes(app)

    # ── 注入 i18n 到所有模板引擎 ──
    from web.i18n import _, current_lang
    import web.routes.dashboard as _dr
    import web.routes.tasks as _tr
    import web.routes.runs as _rr
    for _mod in (_dr, _tr, _rr):
        _mod.TEMPLATES.env.globals["_"] = _
        _mod.TEMPLATES.env.globals["current_lang"] = current_lang

    # ── 语言中间件（从 cookie 读取语言偏好） ──
    @app.middleware("http")
    async def lang_middleware(request, call_next):
        lang_cookie = request.cookies.get("lang", "zh")
        from web.i18n import set_lang
        set_lang(lang_cookie)
        response = await call_next(request)
        return response

    # ── CSP 安全头中间件 ──
    @app.middleware("http")
    async def security_headers_middleware(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # 宽松的 CSP（允许 Bootstrap CDN + 内联脚本）
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "form-action 'self'; "
            "base-uri 'self'"
        )
        response.headers["Content-Security-Policy"] = csp
        return response

    # ── 注册 API 路由（必须放在 register_routes 之后） ──
    from web.api import register_api_routes
    register_api_routes(app)

    # 为了排除 import 干扰，再确认一遍
    if not any(r for r in app.routes if hasattr(r, "path") and r.path == "/"):
        # 手动注册 fallback
        from fastapi import APIRouter
        fallback = APIRouter()
        from web.routes.dashboard import router as dr
        from web.routes.tasks import router as tr
        from web.routes.runs import router as rr
        app.include_router(dr)
        app.include_router(tr)
        app.include_router(rr)

    return app
