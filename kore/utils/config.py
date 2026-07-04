"""应用配置管理"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，从环境变量 / .env 文件 / 默认值加载"""

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 项目路径 ---
    project_root: Path = Path.cwd()
    data_dir: Path = Path.cwd() / "data"
    logs_dir: Path = Path.cwd() / "logs"

    # --- 数据库 ---
    database_url: str = "sqlite:///./data/agent.db"

    # --- 日志 ---
    log_level: str = "INFO"
    log_format: str = "json"  # json | text
    log_max_bytes: int = 10 * 1024 * 1024  # 10 MB
    log_backup_count: int = 5

    # --- 调度器 ---
    scheduler_reload_interval: int = 60  # 秒
    scheduler_timezone: str = "Asia/Shanghai"

    # --- 任务执行 ---
    task_default_timeout: int = 300  # 5 分钟
    task_max_concurrent: int = 10
    task_retry_default_delay: float = 5.0  # 秒
    task_retry_max_attempts: int = 3

    # --- 守护进程 ---
    daemon_pid_file: str = "data/agent.pid"
    daemon_host: str = "127.0.0.1"
    daemon_port: int = 18080

    # --- 二期 Web ---
    web_host: str = "127.0.0.1"
    web_port: int = 18081
    web_secret_key: str = "change-me-in-production"

    # --- LLM / AI ---
    # 优先从 AGENT_OPENAI_API_KEY 读取，也兼容标准 OPENAI_API_KEY
    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com"
    openai_model: str = "deepseek-v4-flash"
    llm_max_history: int = 20


settings = Settings()

# --- 兼容直接的环境变量读取（不依赖 AGENT_ 前缀）---
# 从项目根目录读取 .env
_env_candidates = [
    Path(__file__).resolve().parent.parent.parent / ".env",  # 项目根目录（最可靠）
    Path(".env"),
]
for _env_file in _env_candidates:
    if _env_file.exists():
        for _line in _env_file.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                if _k == "OPENAI_API_KEY" and not settings.openai_api_key:
                    settings.openai_api_key = _v
                elif _k == "OPENAI_BASE_URL" and (not settings.openai_base_url or settings.openai_base_url == "https://api.deepseek.com"):
                    settings.openai_base_url = _v
                elif _k == "OPENAI_MODEL" and (not settings.openai_model or settings.openai_model == "deepseek-v4-flash"):
                    settings.openai_model = _v

# 确保数据目录和日志目录存在（基于项目根目录）
_project_root = Path(__file__).resolve().parent.parent.parent
_data_dir = _project_root / "data"
_logs_dir = _project_root / "logs"
settings.data_dir = _data_dir
settings.logs_dir = _logs_dir
settings.project_root = _project_root
settings.database_url = f"sqlite:///{_data_dir / 'agent.db'}"
_data_dir.mkdir(parents=True, exist_ok=True)
_logs_dir.mkdir(parents=True, exist_ok=True)
