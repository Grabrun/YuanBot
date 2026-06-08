"""数据库迁移工具

支持 SQLite → MySQL 数据迁移。

设计参考: infrastructure-deployment-system.md 迁移工具章节
"""

from __future__ import annotations

import contextlib
import sqlite3
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# SQLite 默认路径
DEFAULT_SQLITE_PATH = "data/yuanbot.db"

# 需要迁移的表及其主键（用于 upsert 冲突处理）
MIGRATION_TABLES = {
    "users": "user_id",
    "conversations": "conversation_id",
    "messages": "message_id",
    "user_facts": "fact_id",
    "episodic_memories": "memory_id",
    "emotion_records": "record_id",
    "user_profiles": "user_id",
    "proactive_tasks": "task_id",
    "user_proactive_settings": "user_id",
    "persona_switch_history": "id",
    "api_keys": "user_id",
}


class MigrationError(Exception):
    """迁移过程中的错误"""


class DatabaseMigrator:
    """SQLite → MySQL 数据迁移器

    使用场景:
        1. 开发环境使用 SQLite，部署时迁移到 MySQL
        2. 从 SQLite 备份恢复到 MySQL
        3. 一次性批量迁移，不支持增量同步

    注意事项:
        - 迁移前请确保 MySQL 目标数据库已创建
        - 建议先 dry-run 检查兼容性
        - 迁移过程中会锁定源数据库（只读）
    """

    def __init__(
        self,
        sqlite_path: str = DEFAULT_SQLITE_PATH,
        mysql_config: dict[str, Any] | None = None,
    ):
        """初始化迁移器

        Args:
            sqlite_path: SQLite 数据库文件路径
            mysql_config: MySQL 连接配置 {
                "host": "localhost",
                "port": 3306,
                "user": "yuanbot",
                "password": "***",
                "database": "yuanbot",
            }
        """
        self.sqlite_path = Path(sqlite_path)
        self.mysql_config = mysql_config or {}
        self._sqlite_conn: sqlite3.Connection | None = None
        self._mysql_conn: Any = None

    def validate_source(self) -> dict[str, Any]:
        """验证源数据库（SQLite）

        Returns:
            验证结果，包含表信息和行数统计
        """
        if not self.sqlite_path.exists():
            raise MigrationError(f"SQLite 数据库不存在: {self.sqlite_path}")

        conn = sqlite3.connect(str(self.sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()

            # 获取所有表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            all_tables = [row[0] for row in cursor.fetchall()]

            # 统计每个迁移表的行数
            table_stats = {}
            for table_name in MIGRATION_TABLES:
                if table_name in all_tables:
                    cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
                    count = cursor.fetchone()[0]
                    table_stats[table_name] = count
                else:
                    table_stats[table_name] = None  # 表不存在

            return {
                "valid": True,
                "path": str(self.sqlite_path),
                "size_mb": round(self.sqlite_path.stat().st_size / (1024 * 1024), 2),
                "total_tables": len(all_tables),
                "migration_tables": table_stats,
                "total_rows": sum(v for v in table_stats.values() if v is not None),
            }
        finally:
            conn.close()

    def validate_target(self) -> dict[str, Any]:
        """验证目标数据库（MySQL）

        Returns:
            验证结果
        """
        try:
            import pymysql
        except ImportError:
            return {
                "valid": False,
                "error": "pymysql 未安装，请运行: pip install pymysql",
            }

        try:
            conn = pymysql.connect(
                host=self.mysql_config.get("host", "localhost"),
                port=self.mysql_config.get("port", 3306),
                user=self.mysql_config.get("user", "yuanbot"),
                password=self.mysql_config.get("password", ""),
                database=self.mysql_config.get("database", "yuanbot"),
                charset="utf8mb4",
            )
            cursor = conn.cursor()

            # 获取目标数据库的表
            cursor.execute("SHOW TABLES")
            all_tables = [row[0] for row in cursor.fetchall()]

            # 检查每个迁移目标表是否存在
            table_status = {}
            for table_name in MIGRATION_TABLES:
                if table_name in all_tables:
                    cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                    count = cursor.fetchone()[0]
                    table_status[table_name] = {"exists": True, "rows": count}
                else:
                    table_status[table_name] = {"exists": False, "rows": 0}

            cursor.close()
            conn.close()

            return {
                "valid": True,
                "host": self.mysql_config.get("host", "localhost"),
                "database": self.mysql_config.get("database", "yuanbot"),
                "tables": table_status,
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
            }

    def _get_sqlite_connection(self) -> sqlite3.Connection:
        """获取 SQLite 连接"""
        if self._sqlite_conn is None:
            self._sqlite_conn = sqlite3.connect(
                str(self.sqlite_path),
                check_same_thread=False,
            )
            self._sqlite_conn.row_factory = sqlite3.Row
        return self._sqlite_conn

    def _get_mysql_connection(self):
        """获取 MySQL 连接"""
        import pymysql

        if self._mysql_conn is None or not self._mysql_conn.open:
            self._mysql_conn = pymysql.connect(
                host=self.mysql_config.get("host", "localhost"),
                port=self.mysql_config.get("port", 3306),
                user=self.mysql_config.get("user", "yuanbot"),
                password=self.mysql_config.get("password", ""),
                database=self.mysql_config.get("database", "yuanbot"),
                charset="utf8mb4",
                autocommit=False,
            )
        return self._mysql_conn

    def _get_table_columns(self, table_name: str, db: str = "sqlite") -> list[str]:
        """获取表的列名列表"""
        if db == "sqlite":
            conn = self._get_sqlite_connection()
            cursor = conn.execute(f"PRAGMA table_info([{table_name}])")
            return [row[1] for row in cursor.fetchall()]
        else:
            conn = self._get_mysql_connection()
            cursor = conn.cursor()
            cursor.execute(f"DESCRIBE `{table_name}`")
            columns = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return columns

    def _migrate_table(
        self,
        table_name: str,
        batch_size: int = 1000,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """迁移单个表的数据

        Args:
            table_name: 表名
            batch_size: 批量插入大小
            dry_run: 是否只统计不写入

        Returns:
            迁移结果
        """
        sqlite_conn = self._get_sqlite_connection()

        # 检查表是否存在
        cursor = sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        if cursor.fetchone() is None:
            return {"table": table_name, "status": "skipped", "reason": "表不存在"}

        # 获取列信息
        sqlite_cols = self._get_table_columns(table_name, "sqlite")
        if not sqlite_cols:
            return {"table": table_name, "status": "skipped", "reason": "无法获取列信息"}

        # 统计总行数
        cursor = sqlite_conn.execute(f"SELECT COUNT(*) FROM [{table_name}]")
        total_rows = cursor.fetchone()[0]

        if total_rows == 0:
            return {"table": table_name, "status": "done", "rows": 0}

        if dry_run:
            return {
                "table": table_name,
                "status": "dry_run",
                "rows": total_rows,
                "columns": sqlite_cols,
            }

        # 获取 MySQL 端的列（用于交叉检查）
        try:
            mysql_cols = self._get_table_columns(table_name, "mysql")
        except Exception as e:
            return {
                "table": table_name,
                "status": "error",
                "reason": f"MySQL 端表不存在或无法访问: {e}",
            }

        # 取交集列（只迁移两边都有的列）
        common_cols = [c for c in sqlite_cols if c in mysql_cols]
        if not common_cols:
            return {
                "table": table_name,
                "status": "error",
                "reason": "没有共同的列",
            }

        # 构建 INSERT 语句
        col_list = ", ".join(f"`{c}`" for c in common_cols)
        placeholders = ", ".join(["%s"] * len(common_cols))
        insert_sql = f"INSERT INTO `{table_name}` ({col_list}) VALUES ({placeholders})"

        # 主键列用于 ON DUPLICATE KEY UPDATE
        pk_col = MIGRATION_TABLES.get(table_name)
        if pk_col and pk_col in common_cols:
            update_cols = [c for c in common_cols if c != pk_col]
            if update_cols:
                update_parts = ", ".join(f"`{c}`=VALUES(`{c}`)" for c in update_cols)
                insert_sql += f" ON DUPLICATE KEY UPDATE {update_parts}"

        # 批量读取并写入
        mysql_conn = self._get_mysql_connection()
        mysql_cursor = mysql_conn.cursor()

        migrated = 0
        errors = 0
        start_time = time.time()

        # 使用 SQLite 流式读取
        offset = 0
        while offset < total_rows:
            rows = sqlite_conn.execute(
                f"SELECT {', '.join(f'[{c}' + ']' for c in common_cols)} "
                f"FROM [{table_name}] LIMIT {batch_size} OFFSET {offset}"
            ).fetchall()

            if not rows:
                break

            # 批量插入
            batch_data = [tuple(row) for row in rows]
            try:
                mysql_cursor.executemany(insert_sql, batch_data)
                mysql_conn.commit()
                migrated += len(batch_data)
            except Exception as e:
                mysql_conn.rollback()
                errors += len(batch_data)
                logger.error(
                    "batch_migration_error",
                    table=table_name,
                    offset=offset,
                    error=str(e),
                )

            offset += batch_size

        elapsed = time.time() - start_time

        return {
            "table": table_name,
            "status": "done",
            "total_rows": total_rows,
            "migrated": migrated,
            "errors": errors,
            "elapsed_seconds": round(elapsed, 2),
        }

    def run_migration(
        self,
        tables: list[str] | None = None,
        batch_size: int = 1000,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """执行完整迁移

        Args:
            tables: 要迁移的表列表，None 表示全部
            batch_size: 批量大小
            dry_run: 是否只统计不写入

        Returns:
            迁移结果汇总
        """
        if tables is None:
            tables = list(MIGRATION_TABLES.keys())

        # 验证源
        source_info = self.validate_source()
        if not source_info["valid"]:
            return {"success": False, "error": f"源数据库无效: {source_info}"}

        # 验证目标（非 dry_run 时）
        if not dry_run:
            target_info = self.validate_target()
            if not target_info["valid"]:
                return {"success": False, "error": f"目标数据库无效: {target_info}"}

        logger.info(
            "migration_started",
            source=str(self.sqlite_path),
            tables=len(tables),
            dry_run=dry_run,
        )

        results = []
        total_migrated = 0
        total_errors = 0

        for table_name in tables:
            logger.info("migrating_table", table=table_name)
            result = self._migrate_table(
                table_name=table_name,
                batch_size=batch_size,
                dry_run=dry_run,
            )
            results.append(result)

            if result.get("migrated"):
                total_migrated += result["migrated"]
            if result.get("errors"):
                total_errors += result["errors"]

        # 关闭连接
        self.close()

        return {
            "success": total_errors == 0,
            "dry_run": dry_run,
            "tables_processed": len(results),
            "total_migrated": total_migrated,
            "total_errors": total_errors,
            "details": results,
        }

    def close(self) -> None:
        """关闭所有数据库连接"""
        if self._sqlite_conn:
            self._sqlite_conn.close()
            self._sqlite_conn = None
        if self._mysql_conn:
            with contextlib.suppress(Exception):
                self._mysql_conn.close()
            self._mysql_conn = None
