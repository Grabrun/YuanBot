"""基础架构与部署系统

配置管理、数据库抽象和部署支持。
"""

from yuanbot.infrastructure.cache_store import CacheStore
from yuanbot.infrastructure.config_loader import ConfigLoader
from yuanbot.infrastructure.database import DatabaseConfig, DatabaseManager, DatabaseType
from yuanbot.infrastructure.graph_store import GraphStore
from yuanbot.infrastructure.sqlite_store import SQLiteStore
from yuanbot.infrastructure.vector_store import VectorStore

# aiomysql 为可选依赖
try:
    from yuanbot.infrastructure.mysql_store import MySQLStore
except ImportError:
    MySQLStore = None  # type: ignore[assignment,misc]

__all__ = [
    "CacheStore",
    "ConfigLoader",
    "DatabaseConfig",
    "DatabaseManager",
    "DatabaseType",
    "GraphStore",
    "MySQLStore",
    "SQLiteStore",
    "VectorStore",
]
