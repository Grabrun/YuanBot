"""统一数据库管理器

协调 SQLite 存储、向量存储和缓存存储，提供统一的初始化和关闭接口。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog

from yuanbot.infrastructure.cache_store import CacheStore
from yuanbot.infrastructure.graph_store import GraphStore
from yuanbot.infrastructure.sqlite_store import SQLiteStore
from yuanbot.infrastructure.vector_store import VectorStore

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
    # 向量存储配置
    use_milvus: bool = False
    milvus_uri: str | None = None
    # 缓存配置
    redis_url: str | None = None
    # 缓存 TTL 配置
    working_memory_ttl: int = 3600  # 工作记忆缓存 TTL（秒）
    # 知识图谱配置
    graph_db_path: str | None = None  # Kuzu 数据库路径（None 则使用内存图）


class DatabaseManager:
    """统一数据库管理器

    职责：
    1. 管理 SQLite 存储（事实记忆、情景记忆元数据、用户画像、情感记录、身份映射）
    2. 管理向量存储（情景记忆向量、语义检索）
    3. 管理缓存存储（工作记忆、主动交互锁）
    4. 提供统一的初始化和关闭接口

    使用方式：
        config = DatabaseConfig(sqlite_path="data/yuanbot.db")
        db = DatabaseManager(config)
        await db.initialize()

        # 使用各存储
        await db.sqlite.save_fact_memory(...)
        await db.vector.add_vector(...)
        await db.cache.get_working_memory(...)
    """

    def __init__(self, config: DatabaseConfig | None = None):
        self._config = config or DatabaseConfig()
        self._initialized = False

        # 初始化各存储组件
        self._sqlite = SQLiteStore(db_path=self._config.sqlite_path)
        self._vector = VectorStore(
            use_milvus=self._config.use_milvus,
            milvus_uri=self._config.milvus_uri,
        )
        self._cache = CacheStore(redis_url=self._config.redis_url)
        self._graph = GraphStore(db_path=self._config.graph_db_path)

    @property
    def db_type(self) -> DatabaseType:
        return self._config.db_type

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def sqlite(self) -> SQLiteStore:
        """SQLite 存储"""
        return self._sqlite

    @property
    def vector(self) -> VectorStore:
        """向量存储"""
        return self._vector

    @property
    def cache(self) -> CacheStore:
        """缓存存储"""
        return self._cache

    @property
    def graph(self) -> GraphStore:
        """知识图谱存储"""
        return self._graph

    @property
    def config(self) -> DatabaseConfig:
        """数据库配置"""
        return self._config

    async def initialize(self) -> None:
        """初始化所有存储组件"""
        if self._initialized:
            return

        logger.info(
            "database_initializing",
            db_type=self._config.db_type.value,
            sqlite_path=self._config.sqlite_path,
            vector_backend="milvus" if self._config.use_milvus else "memory",
            cache_backend="redis" if self._config.redis_url else "memory",
        )

        # 初始化 SQLite
        await self._sqlite.initialize()

        # 初始化向量存储
        await self._vector.initialize()

        # 初始化缓存
        await self._cache.initialize()

        self._initialized = True
        logger.info("database_initialized", db_type=self._config.db_type.value)

    async def close(self) -> None:
        """关闭所有存储组件"""
        await self._sqlite.close()
        await self._vector.close()
        await self._cache.close()
        await self._graph.close()
        self._initialized = False
        logger.info("database_closed")

    def get_connection_info(self) -> dict[str, Any]:
        """获取数据库连接信息"""
        return {
            "db_type": self._config.db_type.value,
            "initialized": self._initialized,
            "sqlite": {
                "path": self._config.sqlite_path,
                "initialized": self._sqlite.is_initialized,
            },
            "vector": {
                "backend": "milvus" if self._config.use_milvus else "memory",
                "initialized": self._vector.is_initialized,
            },
            "cache": {
                "backend": self._cache.backend,
                "initialized": self._cache.is_initialized,
            },
            "graph": {
                "backend": "kuzu" if self._graph.is_kuzu else "memory",
                "initialized": True,
            },
        }
