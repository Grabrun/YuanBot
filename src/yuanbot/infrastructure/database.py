"""数据库抽象层

提供统一的数据库接口，支持 SQLite（默认）和 MySQL（可选）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class DatabaseType(StrEnum):
    """数据库类型"""

    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"


@dataclass
class DatabaseConfig:
    """数据库配置"""

    db_type: DatabaseType = DatabaseType.SQLITE
    # SQLite 配置
    sqlite_path: str = "data/yuanbot.db"
    # MySQL/PostgreSQL 配置
    host: str = "localhost"
    port: int = 3306
    database: str = "yuanbot"
    username: str = ""
    password: str = ""
    # 通用配置
    pool_size: int = 5
    echo: bool = False


class DatabaseManager:
    """数据库管理器

    职责：
    1. 管理数据库连接
    2. 提供统一的数据访问接口
    3. 支持 SQLite 和 MySQL 的无缝切换

    注意：当前版本使用内存存储作为默认实现。
    后续版本将集成 SQLAlchemy 或直接使用 asyncpg/aiomysql。
    """

    def __init__(self, config: DatabaseConfig | None = None):
        self._config = config or DatabaseConfig()
        self._initialized = False
        # 内存存储（用于开发和测试）
        self._store: dict[str, dict[str, Any]] = {}

    @property
    def db_type(self) -> DatabaseType:
        return self._config.db_type

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(self) -> None:
        """初始化数据库连接"""
        if self._initialized:
            return

        logger.info(
            "database_initializing",
            db_type=self._config.db_type.value,
        )

        if self._config.db_type == DatabaseType.SQLITE:
            await self._init_sqlite()
        elif self._config.db_type == DatabaseType.MYSQL:
            await self._init_mysql()
        elif self._config.db_type == DatabaseType.POSTGRESQL:
            await self._init_postgresql()

        self._initialized = True
        logger.info("database_initialized", db_type=self._config.db_type.value)

    async def close(self) -> None:
        """关闭数据库连接"""
        self._initialized = False
        logger.info("database_closed")

    async def _init_sqlite(self) -> None:
        """初始化 SQLite"""
        # 确保数据目录存在
        from pathlib import Path

        db_path = Path(self._config.sqlite_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("sqlite_ready", path=str(db_path))

    async def _init_mysql(self) -> None:
        """初始化 MySQL 连接池"""
        logger.info(
            "mysql_config",
            host=self._config.host,
            port=self._config.port,
            database=self._config.database,
        )

    async def _init_postgresql(self) -> None:
        """初始化 PostgreSQL 连接池"""
        logger.info(
            "postgresql_config",
            host=self._config.host,
            port=self._config.port,
            database=self._config.database,
        )

    def get_connection_info(self) -> dict[str, Any]:
        """获取数据库连接信息"""
        return {
            "db_type": self._config.db_type.value,
            "initialized": self._initialized,
            "sqlite_path": self._config.sqlite_path
            if self._config.db_type == DatabaseType.SQLITE
            else None,
            "host": self._config.host
            if self._config.db_type != DatabaseType.SQLITE
            else None,
        }
