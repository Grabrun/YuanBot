"""日志配置模块

提供结构化日志的文件输出、日志轮转和动态级别调整。

设计参考: infrastructure-deployment-system.md 第6章 - 日志与监控
"""

from __future__ import annotations

import contextlib
import logging
import logging.handlers
import os
from pathlib import Path
from typing import Any

import structlog

# 默认配置
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_FILE = "yuanbot.log"
DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50MB per file
DEFAULT_BACKUP_COUNT = 30  # 保留 30 天
DEFAULT_LOG_LEVEL = "INFO"

# 支持的日志级别映射
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

# 全局文件 handler 引用（用于动态调整级别）
_file_handler: logging.handlers.TimedRotatingFileHandler | None = None
_current_level: str = DEFAULT_LOG_LEVEL


def _get_log_dir() -> Path:
    """获取日志目录，支持环境变量覆盖"""
    log_dir = os.environ.get("YUANBOT_LOG_DIR", DEFAULT_LOG_DIR)
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_file_logging(
    log_dir: str | None = None,
    log_file: str = DEFAULT_LOG_FILE,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    level: str = DEFAULT_LOG_LEVEL,
) -> logging.handlers.TimedRotatingFileHandler:
    """配置日志文件输出和轮转

    Args:
        log_dir: 日志目录，默认为 logs/
        log_file: 日志文件名
        max_bytes: 单个日志文件最大字节数
        backup_count: 保留的备份文件数量
        level: 初始日志级别

    Returns:
        配置好的文件 handler
    """
    global _file_handler, _current_level

    if log_dir is None:
        log_dir_path = _get_log_dir()
    else:
        log_dir_path = Path(log_dir)
        log_dir_path.mkdir(parents=True, exist_ok=True)

    log_path = log_dir_path / log_file

    # 使用 TimedRotatingFileHandler 实现按天轮转
    handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(log_path),
        when="midnight",
        interval=1,
        backupCount=backup_count,
        encoding="utf-8",
        delay=True,  # 延迟创建文件直到首次写入
    )
    handler.suffix = "%Y-%m-%d"

    # 同时限制单个文件大小
    # TimedRotatingFileHandler 不直接支持 maxBytes，
    # 但我们通过每天轮转 + backupCount 来控制总大小
    handler.setLevel(LOG_LEVELS.get(level.upper(), logging.INFO))

    # JSON 格式化器
    formatter = logging.Formatter(
        '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)

    # 添加到 root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    _file_handler = handler
    _current_level = level.upper()

    return handler


def set_log_level(level: str) -> dict[str, Any]:
    """动态调整日志级别

    同时调整标准 logging 和 structlog 的级别。

    Args:
        level: 目标级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)

    Returns:
        操作结果
    """
    global _current_level

    level_upper = level.upper()
    if level_upper not in LOG_LEVELS:
        return {
            "success": False,
            "error": f"不支持的日志级别: {level}",
            "supported": list(LOG_LEVELS.keys()),
        }

    numeric_level = LOG_LEVELS[level_upper]

    # 调整 root logger 级别
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # 调整文件 handler 级别
    if _file_handler is not None:
        _file_handler.setLevel(numeric_level)

    # 调整 structlog 级别
    with contextlib.suppress(Exception):  # structlog 配置可能尚未初始化
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        )

    old_level = _current_level
    _current_level = level_upper

    return {
        "success": True,
        "old_level": old_level,
        "new_level": level_upper,
    }


def get_log_status() -> dict[str, Any]:
    """获取当前日志配置状态

    Returns:
        日志配置信息
    """
    log_dir_path = _get_log_dir()
    log_files = sorted(log_dir_path.glob("*.log*"), key=lambda f: f.stat().st_mtime, reverse=True)

    total_size = sum(f.stat().st_size for f in log_files)

    return {
        "current_level": _current_level,
        "log_dir": str(log_dir_path),
        "log_files": [
            {
                "name": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "modified": f.stat().st_mtime,
            }
            for f in log_files[:10]  # 最多返回 10 个
        ],
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "file_handler_active": _file_handler is not None,
    }
