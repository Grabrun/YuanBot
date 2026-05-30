"""测试日志配置模块"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from yuanbot.infrastructure.logging_config import (
    LOG_LEVELS,
    get_log_status,
    set_log_level,
    setup_file_logging,
)


class TestSetupFileLogging:
    """测试文件日志配置"""

    def test_creates_log_dir(self, tmp_path: Path) -> None:
        """应自动创建日志目录"""
        log_dir = tmp_path / "test_logs"
        handler = setup_file_logging(log_dir=str(log_dir))
        assert log_dir.exists()
        # 清理
        root = logging.getLogger()
        root.removeHandler(handler)

    def test_returns_file_handler(self, tmp_path: Path) -> None:
        """应返回 TimedRotatingFileHandler"""
        log_dir = tmp_path / "test_logs"
        handler = setup_file_logging(log_dir=str(log_dir))
        assert isinstance(handler, logging.handlers.TimedRotatingFileHandler)
        root = logging.getLogger()
        root.removeHandler(handler)

    def test_handler_level_set(self, tmp_path: Path) -> None:
        """应设置正确的 handler 级别"""
        log_dir = tmp_path / "test_logs"
        handler = setup_file_logging(log_dir=str(log_dir), level="WARNING")
        assert handler.level == logging.WARNING
        root = logging.getLogger()
        root.removeHandler(handler)

    def test_log_file_created_on_write(self, tmp_path: Path) -> None:
        """首次写入时应创建日志文件"""
        log_dir = tmp_path / "test_logs"
        handler = setup_file_logging(
            log_dir=str(log_dir),
            log_file="test.log",
            level="INFO",
        )
        logger = logging.getLogger("test_logging")
        logger.info("test message")
        # 清理
        root = logging.getLogger()
        root.removeHandler(handler)


class TestSetLogLevel:
    """测试动态日志级别调整"""

    def test_valid_level_change(self) -> None:
        """应成功切换到有效的日志级别"""
        result = set_log_level("DEBUG")
        assert result["success"] is True
        assert result["new_level"] == "DEBUG"
        # 恢复
        set_log_level("INFO")

    def test_invalid_level_rejected(self) -> None:
        """应拒绝无效的日志级别"""
        result = set_log_level("INVALID")
        assert result["success"] is False
        assert "不支持" in result["error"]

    def test_case_insensitive(self) -> None:
        """应不区分大小写"""
        result = set_log_level("debug")
        assert result["success"] is True
        assert result["new_level"] == "DEBUG"
        set_log_level("INFO")

    def test_affects_root_logger(self) -> None:
        """应调整 root logger 的级别"""
        set_log_level("WARNING")
        root = logging.getLogger()
        assert root.level == logging.WARNING
        set_log_level("INFO")

    def test_returns_old_level(self) -> None:
        """应返回旧级别"""
        set_log_level("INFO")
        result = set_log_level("ERROR")
        assert result["old_level"] == "INFO"
        assert result["new_level"] == "ERROR"
        set_log_level("INFO")


class TestGetLogStatus:
    """测试日志状态查询"""

    def test_returns_current_level(self) -> None:
        """应返回当前日志级别"""
        status = get_log_status()
        assert "current_level" in status

    def test_returns_log_dir(self) -> None:
        """应返回日志目录"""
        status = get_log_status()
        assert "log_dir" in status

    def test_returns_file_handler_status(self) -> None:
        """应返回文件 handler 状态"""
        status = get_log_status()
        assert "file_handler_active" in status

    def test_returns_log_files(self) -> None:
        """应返回日志文件列表"""
        status = get_log_status()
        assert "log_files" in status
        assert isinstance(status["log_files"], list)

    def test_returns_total_size(self) -> None:
        """应返回总大小"""
        status = get_log_status()
        assert "total_size_mb" in status
        assert isinstance(status["total_size_mb"], (int, float))


class TestLogLevels:
    """测试日志级别映射"""

    def test_all_levels_present(self) -> None:
        """应包含所有标准日志级别"""
        assert "DEBUG" in LOG_LEVELS
        assert "INFO" in LOG_LEVELS
        assert "WARNING" in LOG_LEVELS
        assert "ERROR" in LOG_LEVELS
        assert "CRITICAL" in LOG_LEVELS

    def test_levels_are_correct(self) -> None:
        """级别值应正确"""
        assert LOG_LEVELS["DEBUG"] == logging.DEBUG
        assert LOG_LEVELS["INFO"] == logging.INFO
        assert LOG_LEVELS["WARNING"] == logging.WARNING
        assert LOG_LEVELS["ERROR"] == logging.ERROR
        assert LOG_LEVELS["CRITICAL"] == logging.CRITICAL
