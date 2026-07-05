"""应用配置管理"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（基于本文件位置计算，不受 CWD 影响）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """全局配置，从环境变量 / .env 文件 / 默认值加载"""

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=_ENV_FILE,  # 使用绝对路径，不受 CWD 影响
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
    log_console_silent: bool = False  # REPL 模式静默控制台输出

    # --- 调度器 ---
    scheduler_reload_interval: int = 60  # 秒
    scheduler_timezone: str = "Asia/Shanghai"

    # --- 数据保留 ---
    data_retention_days: int = 90
    max_runs_per_task: int = 1000

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
    web_secret_key: str = ""  # Session 签名密钥，必须通过环境变量 AGENT_WEB_SECRET_KEY 设置
    web_admin_password: str = ""  # Web 管理密码，默认同 web_secret_key；可通过 AGENT_WEB_ADMIN_PASSWORD 单独设置

    # --- LLM / AI ---
    # 兼容 AGENT_ 前缀和标准的 OPENAI_ 前缀
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("AGENT_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    openai_base_url: str = Field(
        default="https://api.deepseek.com",
        validation_alias=AliasChoices("AGENT_OPENAI_BASE_URL", "OPENAI_BASE_URL"),
    )
    openai_model: str = Field(
        default="deepseek-v4-flash",
        validation_alias=AliasChoices("AGENT_OPENAI_MODEL", "OPENAI_MODEL"),
    )
    llm_max_history: int = 20


settings = Settings()

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
