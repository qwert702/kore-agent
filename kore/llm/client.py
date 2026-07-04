"""OpenAI 兼容客户端封装（指向 DeepSeek）"""

from __future__ import annotations

from openai import OpenAI

from kore.utils.config import settings

_client: OpenAI | None = None
_model: str = ""


def get_client() -> OpenAI:
    """获取 OpenAI 客户端（惰性初始化）"""
    global _client
    if _client is None:
        api_key = settings.openai_api_key or settings.openai_base_url
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY 未设置，请在 .env 文件中配置或设置环境变量"
            )
        if api_key == settings.openai_base_url:
            raise RuntimeError(
                "OPENAI_API_KEY 未设置，当前值误用了 base_url"
            )
        _client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or "https://api.deepseek.com",
        )
    return _client


def get_model() -> str:
    """获取当前模型名称"""
    global _model
    if not _model:
        _model = settings.openai_model or "deepseek-v4-flash"
    return _model


def check_available() -> bool:
    """检查 AI 服务是否可用（调用 chat API 做轻量验证）

    DeepSeek 的 /models 端点行为与 OpenAI 不一致，
    改用发一条空消息到 chat API 来验证连通性更可靠。
    """
    if not settings.openai_api_key:
        return False
    try:
        client = get_client()
        # 发一条极短的消息验证 API 连通性
        resp = client.chat.completions.create(
            model=get_model(),
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
        )
        return bool(resp.choices)
    except Exception:
        return False
