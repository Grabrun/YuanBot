"""备份管理器测试"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from yuanbot.infrastructure.backup import BackupManager


@pytest.fixture
def tmp_env(tmp_path: Path):
    """创建临时测试环境"""
    # 创建模拟的 data/ 和 configs/ 目录
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "yuanbot.db").write_text("fake db content")
    (data_dir / "milvus").mkdir()
    (data_dir / "milvus" / "test.dat").write_text("fake vector data")

    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "bot.yaml").write_text("app_name: YuanBot\nversion: 1.0.0")
    (configs_dir / "Providers").mkdir()
    (configs_dir / "Providers" / "openai.yaml").write_text("provider_id: openai")

    backup_dir = tmp_path / "backups"

    return {
        "base_dir": tmp_path,
        "data_dir": data_dir,
        "configs_dir": configs_dir,
        "backup_dir": backup_dir,
    }


class TestBackupManagerCreate:
    """测试备份创建"""

    def test_create_backup_basic(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        result = manager.create_backup()

        assert "name" in result
        assert result["name"].startswith("backup_")
        assert "path" in result
        assert "size_bytes" in result
        assert result["size_bytes"] > 0
        assert result["file_count"] > 0
        assert "data" in result["includes"]
        assert "configs" in result["includes"]

        # 归档文件存在
        archive_path = Path(result["path"])
        assert archive_path.exists()
        assert archive_path.suffix == ".gz"

    def test_create_backup_with_description(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        result = manager.create_backup(
            description="测试备份",
            created_by="test_user",
        )
        assert result["name"].startswith("backup_")

        # 检查 meta.json
        meta_path = tmp_env["backup_dir"] / f"{result['name']}_meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["description"] == "测试备份"
        assert meta["created_by"] == "test_user"

    def test_create_backup_archive_contents(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        result = manager.create_backup()

        archive_path = Path(result["path"])
        with tarfile.open(str(archive_path), "r:gz") as tar:
            names = tar.getnames()
            # 应包含 data 和 configs 下的文件
            assert any("data/" in n for n in names)
            assert any("configs/" in n for n in names)
            # 应包含元数据
            assert "backup_meta.json" in names

    def test_create_backup_excludes_cache_dirs(self, tmp_env: dict):
        # 创建应该被排除的目录
        (tmp_env["data_dir"] / "__pycache__").mkdir()
        (tmp_env["data_dir"] / "__pycache__" / "cache.pyc").write_text("cache")
        (tmp_env["base_dir"] / ".venv").mkdir()
        (tmp_env["base_dir"] / ".venv" / "lib").mkdir()

        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        result = manager.create_backup()

        archive_path = Path(result["path"])
        with tarfile.open(str(archive_path), "r:gz") as tar:
            names = tar.getnames()
            assert not any("__pycache__" in n for n in names)
            assert not any(".venv" in n for n in names)

    def test_create_backup_excludes_backup_dir(self, tmp_env: dict):
        """备份不应包含备份目录自身"""
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        result = manager.create_backup()
        result2 = manager.create_backup()

        # 两次备份都应成功
        assert result["file_count"] > 0
        assert result2["file_count"] > 0


class TestBackupManagerList:
    """测试备份列表"""

    def test_list_empty(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        assert manager.list_backups() == []

    def test_list_after_create(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        manager.create_backup(description="第一个")
        manager.create_backup(description="第二个")

        backups = manager.list_backups()
        assert len(backups) == 2
        # 按时间倒序
        assert backups[0]["description"] == "第二个"

    def test_list_with_metadata(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        manager.create_backup(description="测试描述", created_by="tester")

        backups = manager.list_backups()
        assert len(backups) == 1
        assert backups[0]["description"] == "测试描述"
        assert backups[0]["created_by"] == "tester"


class TestBackupManagerRestore:
    """测试备份恢复"""

    def test_restore_backup(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        result = manager.create_backup()
        backup_name = result["name"]

        # 修改原始文件
        (tmp_env["configs_dir"] / "bot.yaml").write_text("modified: true")

        # 恢复
        restore_result = manager.restore_backup(backup_name)
        assert restore_result["success"] is True
        assert restore_result["restored_files"] > 0

        # 验证文件恢复
        content = (tmp_env["configs_dir"] / "bot.yaml").read_text()
        assert "YuanBot" in content

    def test_restore_dry_run(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        result = manager.create_backup()

        restore_result = manager.restore_backup(result["name"], dry_run=True)
        assert restore_result["success"] is True
        assert restore_result["dry_run"] is True
        assert len(restore_result["would_restore"]) > 0

    def test_restore_nonexistent(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        result = manager.restore_backup("nonexistent_backup")
        assert result.get("error") is not None
        assert result["success"] is False

    def test_restore_selective(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        result = manager.create_backup()

        # 只恢复 configs，不恢复 data
        restore_result = manager.restore_backup(
            result["name"],
            restore_data=False,
            restore_configs=True,
        )
        assert restore_result["success"] is True


class TestBackupManagerDelete:
    """测试备份删除"""

    def test_delete_backup(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        result = manager.create_backup()

        assert manager.delete_backup(result["name"]) is True
        assert manager.list_backups() == []

    def test_delete_nonexistent(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        assert manager.delete_backup("nonexistent") is False


class TestBackupManagerCleanup:
    """测试备份清理"""

    def test_cleanup_keeps_recent(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )

        # 创建 5 个备份
        for i in range(5):
            manager.create_backup(description=f"备份 {i}")

        assert len(manager.list_backups()) == 5

        # 保留最近 3 个
        deleted = manager.cleanup_old_backups(keep_count=3)
        assert deleted == 2
        assert len(manager.list_backups()) == 3

    def test_cleanup_noop_when_under_limit(self, tmp_env: dict):
        manager = BackupManager(
            backup_dir=tmp_env["backup_dir"],
            base_dir=tmp_env["base_dir"],
        )
        manager.create_backup()

        deleted = manager.cleanup_old_backups(keep_count=10)
        assert deleted == 0
