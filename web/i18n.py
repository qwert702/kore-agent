"""中英文翻译模块 — ContextVar 驱动，零侵入式"""

from __future__ import annotations

from contextvars import ContextVar

# ── 当前语言上下文 ──────────────────────────────────────────
_current_lang: ContextVar[str] = ContextVar("current_lang", default="zh")


def set_lang(lang: str) -> None:
    """设置当前请求的语言（'zh' / 'en'）"""
    _current_lang.set(lang)


def current_lang() -> str:
    """获取当前语言"""
    return _current_lang.get()


# ── 中文翻译表 ────────────────────────────────────────────
LANG_ZH: dict[str, str] = {
    # ── 导航 ──
    "Dashboard": "仪表盘",
    "Tasks": "任务",
    "Run History": "执行记录",
    "Logout": "退出",

    # ── 仪表盘 ──
    "Dashboard Page": "仪表盘",
    "Total Tasks": "总任务数",
    "Active": "运行中",
    "Paused": "已暂停",
    "Today's Runs": "今日执行",
    "Recent Runs": "最近执行记录",
    "System Info": "系统信息",
    "Scheduler": "调度器",
    "Running": "运行中",
    "Not Running": "未启动",
    "Daemon Port": "守护进程端口",
    "Database": "数据库",
    "of": "个",
    "records": "条记录",
    "No run records": "暂无执行记录",

    # ── 任务列表 ──
    "Task List": "任务列表",
    "New Task": "新建任务",
    "Name": "名称",
    "Type": "类型",
    "Schedule": "调度",
    "Last Run": "最近执行",
    "Actions": "操作",
    "No tasks": "暂无任务",
    "Create Your First Task": "新建第一个任务",
    "Confirm delete task": "确定要删除任务",
    "Are you sure?": "确认删除？",

    # ── 任务详情 ──
    "Edit": "编辑",
    "Run": "执行",
    "Delete": "删除",
    "Basic Info": "基本信息",
    "Configuration": "配置",
    "Timeout": "超时",
    "Tags": "标签",
    "Created At": "创建时间",
    "Run ID": "运行ID",
    "Trigger": "触发方式",
    "Duration": "耗时",
    "Exit Code": "退出码",
    "Details": "详情",

    # ── 任务表单 ──
    "New Task Page": "新建任务",
    "Edit Task": "编辑任务",
    "Description": "描述",
    "Config (JSON)": "配置 (JSON)",
    "Schedule Type": "调度类型",
    "Schedule Expression": "调度表达式",
    "Timeout (s)": "超时 (秒)",
    "Tags (comma separated)": "标签 (逗号分隔)",
    "Cancel": "取消",
    "Save": "保存",
    "Create": "创建",
    "shell example": 'shell: {"command": "echo hello"}',
    "http example": 'http: {"url": "https://...", "method": "GET"}',
    "python example": 'python: {"code": "print(\'hello\')"}',
    "None": "无",
    "Required": "必填",

    # ── 执行记录列表 ──
    "All Run Records": "全部执行记录",

    # ── 执行记录详情 ──
    "Run Record": "运行记录",
    "Back to Task": "返回任务",
    "stdout": "标准输出",
    "stderr": "标准错误",
    "Error": "错误",
    "truncated": "已截断",

    # ── 登录 ──
    "kore Admin": "kore 管理",
    "Admin Password": "管理密码",
    "Login": "登录",

    # ── 通用 ──
    "Status": "状态",
    "Time": "时间",
    "ID": "ID",
    "Yes": "是",
    "No": "否",
    "seconds": "秒",
    "ms": "毫秒",
    "Page not found": "页面未找到",
    "Back to Dashboard": "返回仪表盘",
}

# ── 英文翻译表 ──
LANG_EN: dict[str, str] = {
    k: k for k in LANG_ZH  # 中文 key 的英文就是 key 本身
}


# ── 翻译函数 ──────────────────────────────────────────────
TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh": LANG_ZH,
    "en": LANG_EN,
}


def _(key: str, default: str | None = None) -> str:
    """翻译 key 为当前语言。找不到时返回 default 或 key 本身"""
    lang = _current_lang.get()
    table = TRANSLATIONS.get(lang)
    if table is None:
        return default or key
    return table.get(key, default or key)
