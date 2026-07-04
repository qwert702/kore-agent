"""重试机制封装"""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Callable, TypeVar

from kore.utils.logger import get_logger

logger = get_logger("retry")

T = TypeVar("T")


class RetryError(Exception):
    """所有重试耗尽后抛出"""


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """同步函数重试装饰器

    Args:
        max_attempts: 最大重试次数（包含首次）
        delay: 首次重试延迟（秒）
        backoff: 每次重试延迟倍数
        exceptions: 可重试的异常类型
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            current_delay = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts:
                        logger.warning(
                            "重试 %s 第 %d/%d 次失败: %s",
                            func.__name__,
                            attempt,
                            max_attempts,
                            e,
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
            msg = f"{func.__name__} 在 {max_attempts} 次尝试后仍然失败"
            raise RetryError(msg) from last_exc

        return wrapper

    return decorator


def async_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """异步函数重试装饰器"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            current_delay = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts:
                        logger.warning(
                            "重试 %s 第 %d/%d 次失败: %s",
                            func.__name__,
                            attempt,
                            max_attempts,
                            e,
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
            msg = f"{func.__name__} 在 {max_attempts} 次尝试后仍然失败"
            raise RetryError(msg) from last_exc

        return wrapper

    return decorator
