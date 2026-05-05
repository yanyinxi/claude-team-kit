#!/usr/bin/env python3
"""
统一异常处理工具模块

提供标准化的异常处理函数，替代散落在各处的 `except Exception: pass` 模式。

使用方式：
    from harness._core.exceptions import handle_exception, safe_execute
"""
import logging
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def handle_exception(
    e: Exception,
    context: str,
    reraise: bool = False,
    default_return: Any = None,
    log_level: str = "error",
) -> Any:
    """
    统一异常处理

    Args:
        e: 异常对象
        context: 错误上下文描述
        reraise: 是否重新抛出
        default_return: 失败时的默认返回值
        log_level: 日志级别 (debug/info/warning/error/critical)

    Returns:
        default_return 如果不重新抛出
    """
    error_msg = f"{context}: {type(e).__name__}: {e}"

    # 根据日志级别记录
    log_func = getattr(logger, log_level.lower(), logger.error)
    log_func(error_msg)

    if reraise:
        raise

    return default_return


def safe_execute(
    func: Callable[..., T],
    *args,
    default: T = None,
    context: Optional[str] = None,
    reraise: bool = False,
    **kwargs,
) -> T:
    """
    安全执行函数，捕获异常返回默认值

    Args:
        func: 要执行的函数
        *args: 位置参数
        default: 失败时的默认返回值
        context: 错误上下文描述（可选，默认使用函数名）
        reraise: 是否重新抛出异常
        **kwargs: 关键字参数

    Returns:
        函数的返回值，或 default
    """
    func_name = context or func.__name__
    try:
        return func(*args, **kwargs)
    except Exception as e:
        handle_exception(e, f"执行 {func_name} 失败", reraise=reraise, default_return=None)
        return default


def safe_json_loads(
    data: str,
    default: Any = None,
    context: str = "JSON 解析",
) -> Any:
    """
    安全解析 JSON，捕获 json.JSONDecodeError

    Args:
        data: JSON 字符串
        default: 解析失败时的默认返回值
        context: 错误上下文描述

    Returns:
        解析后的对象，或 default
    """
    import json

    try:
        return json.loads(data)
    except (json.JSONDecodeError, ValueError) as e:
        handle_exception(e, context, default_return=default, log_level="warning")
        return default


def safe_file_read(
    file_path: str,
    encoding: str = "utf-8",
    default: str = "",
    context: Optional[str] = None,
) -> str:
    """
    安全读取文件内容

    Args:
        file_path: 文件路径
        encoding: 编码格式
        default: 读取失败时的默认返回值
        context: 错误上下文描述

    Returns:
        文件内容，或 default
    """
    ctx = context or f"读取文件 {file_path}"
    try:
        with open(file_path, "r", encoding=encoding) as f:
            return f.read()
    except (OSError, IOError, UnicodeDecodeError) as e:
        handle_exception(e, ctx, default_return=default, log_level="warning")
        return default


def safe_file_write(
    file_path: str,
    content: str,
    encoding: str = "utf-8",
    context: Optional[str] = None,
) -> bool:
    """
    安全写入文件内容

    Args:
        file_path: 文件路径
        content: 要写入的内容
        encoding: 编码格式
        context: 错误上下文描述

    Returns:
        写入成功返回 True，失败返回 False
    """
    from pathlib import Path

    ctx = context or f"写入文件 {file_path}"
    try:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding=encoding) as f:
            f.write(content)
        return True
    except (OSError, IOError) as e:
        handle_exception(e, ctx, default_return=False, log_level="warning")
        return False


def safe_call_api(
    func: Callable[..., T],
    *args,
    default: T = None,
    context: str = "API 调用",
    max_retries: int = 0,
    **kwargs,
) -> T:
    """
    安全调用 API 或外部服务，支持重试

    Args:
        func: 要执行的函数
        *args: 位置参数
        default: 失败时的默认返回值
        context: 错误上下文描述
        max_retries: 最大重试次数
        **kwargs: 关键字参数

    Returns:
        函数的返回值，或 default
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"{context} 失败，{attempt + 1}/{max_retries + 1} 次尝试: {e}")
            else:
                handle_exception(e, context, default_return=default, log_level="warning")

    return default


# 导出常用异常类型，供外部直接导入使用
__all__ = [
    "handle_exception",
    "safe_execute",
    "safe_json_loads",
    "safe_file_read",
    "safe_file_write",
    "safe_call_api",
    "logger",
]