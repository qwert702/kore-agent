"""数据库引擎和会话管理"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from kore.utils.config import settings


class Base(DeclarativeBase):
    """ORM 基类"""


# 同步引擎（用于 CLI、APScheduler 等同步操作）
sync_engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # 防止 detached 后访问属性报 DetachedInstanceError
)


@contextmanager
def get_sync_session() -> Generator:
    """获取同步会话（上下文管理器）"""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# --- 以下是异步引擎，惰性初始化（需要 aiosqlite） ---

_async_engine: Any = None
_AsyncSessionLocal: Any = None


def _get_async_engine():
    """惰性创建异步引擎（需要安装 aiosqlite）"""
    global _async_engine, _AsyncSessionLocal

    if _async_engine is not None:
        return _async_engine, _AsyncSessionLocal

    try:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        async_database_url = settings.database_url.replace(
            "sqlite:///", "sqlite+aiosqlite:///"
        )

        _async_engine = create_async_engine(
            async_database_url,
            pool_pre_ping=True,
            echo=False,
        )

        _AsyncSessionLocal = async_sessionmaker(
            bind=_async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        return _async_engine, _AsyncSessionLocal
    except ImportError:
        raise ImportError(
            "异步数据库引擎需要 aiosqlite，请安装: pip install aiosqlite"
        )


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[Any, None]:
    """异步会话上下文管理器"""
    _, AsyncSessionLocal = _get_async_engine()
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def init_db() -> None:
    """初始化数据库表（同步操作）+ 自动迁移新增字段"""
    Base.metadata.create_all(sync_engine)
    _migrate_schema()


def _migrate_schema() -> None:
    """自动迁移：为已有表添加缺失的列（SQLite ALTER TABLE ADD COLUMN）"""
    from sqlalchemy import text as sa_text

    migrations = [
        # 链式触发字段
        ("tasks", "trigger_condition", "VARCHAR(16)"),
        ("tasks", "trigger_task_id", "INTEGER REFERENCES tasks(id)"),
        # 通知关联字段
        ("tasks", "notify_on_success", "BOOLEAN DEFAULT 0"),
        ("tasks", "notify_on_failure", "BOOLEAN DEFAULT 1"),
        ("tasks", "notify_channel_ids", "VARCHAR(256) DEFAULT ''"),
    ]

    with sync_engine.connect() as conn:
        for table, column, col_type in migrations:
            try:
                conn.execute(sa_text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
            except Exception:
                conn.rollback()


async def init_async_db() -> None:
    """使用异步引擎初始化数据库表（需要 aiosqlite）"""
    async_engine, _ = _get_async_engine()
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
