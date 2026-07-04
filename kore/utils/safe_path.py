"""路径安全校验工具

防止目录遍历攻击，确保文件操作限定在允许的目录范围内。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


class PathTraversalError(Exception):
    """路径遍历攻击检测"""


def safe_resolve(path: str | Path, base_dir: str | Path | None = None) -> Path:
    """将路径解析为绝对路径，并检查是否在 base_dir 之内

    Args:
        path: 用户传入的路径（可能是相对路径或包含 ..）
        base_dir: 允许的基目录，默认为当前工作目录

    Returns:
        规范化后的绝对路径

    Raises:
        PathTraversalError: 如果解析后的路径不在 base_dir 下
    """
    base = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()
    target = Path(path).resolve()

    # 检查目录遍历
    if base not in target.parents and base != target:
        raise PathTraversalError(
            f"路径遍历攻击检测: {path} -> {target} 不在 {base} 下"
        )

    return target


def safe_listdir(path: str | Path, base_dir: str | Path | None = None) -> list[Path]:
    """安全地列出目录内容

    Args:
        path: 目录路径
        base_dir: 允许的基目录

    Returns:
        目录下的所有文件（不递归）
    """
    resolved = safe_resolve(path, base_dir)
    return [p for p in resolved.iterdir() if p.is_file()]


def safe_glob(
    pattern: str, base_dir: str | Path | None = None
) -> list[Path]:
    """安全地 glob 匹配文件

    Args:
        pattern: glob 模式
        base_dir: 允许的基目录

    Returns:
        匹配的文件列表
    """
    base = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()
    results: list[Path] = []
    for p in base.rglob(pattern):
        if p.is_file():
            results.append(p)
    return results


def is_safe_filename(name: str) -> bool:
    """检查文件名是否安全（不含路径分隔符和危险字符）"""
    return (
        "/" not in name
        and "\\" not in name
        and ".." not in name
        and bool(name)
        and len(name) < 256
    )
