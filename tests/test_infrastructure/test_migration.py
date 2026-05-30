"""测试数据库迁移工具"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock  # noqa: F401

import pytest

from yuanbot.infrastructure.migration import (
    MIGRATION_TABLES,
    DatabaseMigrator,
    MigrationError,
)


@pytest.fixture
def sample_sqlite(tmp_path: Path) -> Path:
    """创建一个示例 SQLite 数据库"""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # 创建一个简单的表
    cursor.execute("""
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            display_name TEXT
        )
    """)
    cursor.execute(
        "INSERT INTO users (user_id, username, display_name) VALUES (?, ?, ?)",
        ("user1", "testuser", "测试用户"),
    )
    cursor.execute(
        "INSERT INTO users (user_id, username, display_name) VALUES (?, ?, ?)",
        ("user2", "admin", "管理员"),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def empty_sqlite(tmp_path: Path) -> Path:
    """创建一个空的 SQLite 数据库"""
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.close()
    return db_path


@pytest.fixture
def nonexistent_path() -> Path:
    """返回一个不存在的路径"""
    return Path("/nonexistent/path/data.db")


class TestMigrationTables:
    """测试迁移表定义"""

    def test_tables_defined(self) -> None:
        """应定义所有需要迁移的表"""
        assert "users" in MIGRATION_TABLES
        assert "conversations" in MIGRATION_TABLES
        assert "messages" in MIGRATION_TABLES

    def test_tables_have_primary_keys(self) -> None:
        """每个表应有主键定义"""
        for table, pk in MIGRATION_TABLES.items():
            assert pk, f"表 {table} 缺少主键定义"


class TestDatabaseMigrator:
    """测试数据库迁移器"""

    def test_init_with_defaults(self) -> None:
        """应能用默认参数初始化"""
        migrator = DatabaseMigrator()
        assert migrator.sqlite_path == Path("data/yuanbot.db")
        assert migrator.mysql_config == {}

    def test_init_with_custom_config(self, sample_sqlite: Path) -> None:
        """应能用自定义参数初始化"""
        config = {"host": "db.example.com", "port": 3307}
        migrator = DatabaseMigrator(
            sqlite_path=str(sample_sqlite),
            mysql_config=config,
        )
        assert migrator.sqlite_path == sample_sqlite
        assert migrator.mysql_config["host"] == "db.example.com"


class TestValidateSource:
    """测试源数据库验证"""

    def test_valid_source(self, sample_sqlite: Path) -> None:
        """应验证有效的源数据库"""
        migrator = DatabaseMigrator(sqlite_path=str(sample_sqlite))
        result = migrator.validate_source()
        assert result["valid"] is True
        assert result["total_rows"] == 2
        assert result["migration_tables"]["users"] == 2

    def test_empty_database(self, empty_sqlite: Path) -> None:
        """应正确处理空数据库"""
        migrator = DatabaseMigrator(sqlite_path=str(empty_sqlite))
        result = migrator.validate_source()
        assert result["valid"] is True
        assert result["total_rows"] == 0

    def test_nonexistent_database(self, nonexistent_path: Path) -> None:
        """不存在的数据库应抛出错误"""
        migrator = DatabaseMigrator(sqlite_path=str(nonexistent_path))
        with pytest.raises(MigrationError, match="不存在"):
            migrator.validate_source()


class TestMigrateTable:
    """测试单表迁移"""

    def test_dry_run_counts_rows(self, sample_sqlite: Path) -> None:
        """dry_run 应只统计不写入"""
        migrator = DatabaseMigrator(sqlite_path=str(sample_sqlite))
        result = migrator._migrate_table("users", dry_run=True)
        assert result["status"] == "dry_run"
        assert result["rows"] == 2

    def test_nonexistent_table_skipped(self, sample_sqlite: Path) -> None:
        """不存在的表应跳过"""
        migrator = DatabaseMigrator(sqlite_path=str(sample_sqlite))
        result = migrator._migrate_table("nonexistent_table")
        assert result["status"] == "skipped"

    def test_close_closes_connections(self, sample_sqlite: Path) -> None:
        """关闭应清理所有连接"""
        migrator = DatabaseMigrator(sqlite_path=str(sample_sqlite))
        # 创建连接
        conn = migrator._get_sqlite_connection()
        assert conn is not None
        # 关闭
        migrator.close()
        assert migrator._sqlite_conn is None


class TestRunMigration:
    """测试完整迁移"""

    def test_dry_run_all_tables(self, sample_sqlite: Path) -> None:
        """dry_run 应处理所有表"""
        migrator = DatabaseMigrator(sqlite_path=str(sample_sqlite))
        result = migrator.run_migration(dry_run=True)
        assert result["dry_run"] is True
        assert result["tables_processed"] > 0

    def test_specific_tables(self, sample_sqlite: Path) -> None:
        """应能指定迁移特定表"""
        migrator = DatabaseMigrator(sqlite_path=str(sample_sqlite))
        result = migrator.run_migration(tables=["users"], dry_run=True)
        assert result["tables_processed"] == 1
        assert result["details"][0]["table"] == "users"
