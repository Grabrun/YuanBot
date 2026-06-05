"""YuanBot 备份与恢复系统

提供完整系统备份/恢复功能：
- data/ 目录（数据库、向量存储、知识图谱、Redis 快照）
- configs/ 目录（所有 YAML 配置）
- 可选 logs/ 目录

备份格式: tar.gz 归档 + meta.json 元数据
支持增量备份和全量备份。

设计参考: infrastructure-deployment-system.md
"""

from __future__ import annotations

import json
import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 默认备份目录
DEFAULT_BACKUP_DIR = Path("data/backups")

# 默认备份包含的目录
DEFAULT_INCLUDE_DIRS = ["data", "configs"]
OPTIONAL_INCLUDE_DIRS = ["logs"]


class BackupManager:
    """备份管理器

    支持全量备份、恢复、列出、清理。
    备份文件为 tar.gz 格式，附带 meta.json 元数据。
    """

    def __init__(
        self,
        backup_dir: Path | str | None = None,
        base_dir: Path | str | None = None,
    ) -> None:
        self._backup_dir = Path(backup_dir) if backup_dir else DEFAULT_BACKUP_DIR
        self._base_dir = Path(base_dir) if base_dir else Path(".")

    @property
    def backup_dir(self) -> Path:
        return self._backup_dir

    def create_backup(
        self,
        include_logs: bool = False,
        description: str = "",
        created_by: str = "system",
    ) -> dict[str, Any]:
        """创建全量备份

        将 data/ 和 configs/ 打包为 tar.gz 归档。

        Args:
            include_logs: 是否包含 logs/ 目录
            description: 备份描述
            created_by: 创建者标识

        Returns:
            备份信息字典，包含 name, path, size_bytes, timestamp 牉
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_name = f"backup_{timestamp}"
        archive_path = self._backup_dir / f"{backup_name}.tar.gz"

        # 确保备份目录存在
        self._backup_dir.mkdir(parents=True, exist_ok=True)

        # 构建要备份的目录列表
        include_dirs = list(DEFAULT_INCLUDE_DIRS)
        if include_logs:
            include_dirs.append("logs")

        # 元数据
        meta: dict[str, Any] = {
            "name": backup_name,
            "timestamp": timestamp,
            "created_at": datetime.now().isoformat(),
            "created_by": created_by,
            "description": description,
            "includes": include_dirs,
            "version": "1.0",
        }

        # 收集备份内容
        file_count = 0
        total_size = 0

        with tarfile.open(str(archive_path), "w:gz") as tar:
            # 添加源目录
            for dir_name in include_dirs:
                dir_path = self._base_dir / dir_name
                if not dir_path.exists():
                    logger.warning("backup_dir_not_found", dir=dir_name)
                    continue

                for file_path in sorted(dir_path.rglob("*")):
                    if not file_path.is_file():
                        continue

                    # 跳过备份目录自身（避免递归）
                    try:
                        file_path.relative_to(self._backup_dir)
                        continue
                    except ValueError:
                        pass

                    # 跳过 __pycache__、.pytest_cache 等
                    parts = file_path.parts
                    if any(
                        p.startswith(".") or p == "__pycache__" or p == ".venv"
                        for p in parts
                    ):
                        continue

                    arcname = str(file_path.relative_to(self._base_dir))
                    tar.add(str(file_path), arcname=arcname)
                    file_count += 1
                    total_size += file_path.stat().st_size

            # 写入元数据到归档
            meta_bytes = json.dumps(meta, indent=2, ensure_ascii=False).encode("utf-8")
            import io

            meta_info = tarfile.TarInfo(name="backup_meta.json")
            meta_info.size = len(meta_bytes)
            tar.addfile(meta_info, io.BytesIO(meta_bytes))

        # 同时保存独立的元数据文件（方便列出备份时快速读取）
        meta_path = self._backup_dir / f"{backup_name}_meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        result = {
            "name": backup_name,
            "path": str(archive_path),
            "size_bytes": archive_path.stat().st_size,
            "size_mb": round(archive_path.stat().st_size / (1024 * 1024), 2),
            "file_count": file_count,
            "total_source_size_mb": round(total_size / (1024 * 1024), 2),
            "timestamp": timestamp,
            "includes": include_dirs,
        }

        logger.info(
            "backup_created",
            name=backup_name,
            size_mb=result["size_mb"],
            file_count=file_count,
        )

        return result

    def list_backups(self) -> list[dict[str, Any]]:
        """列出所有可用备份

        Returns:
            备份信息列表，按时间倒序排列
        """
        if not self._backup_dir.exists():
            return []

        backups: list[dict[str, Any]] = []

        # 方式 1: 读取 meta.json 文件
        for meta_file in sorted(
            self._backup_dir.glob("*_meta.json"), reverse=True
        ):
            try:
                with open(meta_file, encoding="utf-8") as f:
                    meta = json.load(f)
                archive_name = meta.get("name", meta_file.stem.replace("_meta", ""))
                archive_path = self._backup_dir / f"{archive_name}.tar.gz"
                meta["exists"] = archive_path.exists()
                if archive_path.exists():
                    meta["size_bytes"] = archive_path.stat().st_size
                    meta["size_mb"] = round(
                        archive_path.stat().st_size / (1024 * 1024), 2
                    )
                backups.append(meta)
            except Exception:
                continue

        # 方式 2: 如果没有 meta 文件，扫描 tar.gz 文件
        if not backups:
            for archive_file in sorted(
                self._backup_dir.glob("backup_*.tar.gz"), reverse=True
            ):
                name = archive_file.stem.replace(".tar.gz", "")
                backups.append({
                    "name": name,
                    "path": str(archive_file),
                    "size_bytes": archive_file.stat().st_size,
                    "size_mb": round(
                        archive_file.stat().st_size / (1024 * 1024), 2
                    ),
                    "exists": True,
                })

        return backups

    def get_backup_info(self, backup_name: str) -> dict[str, Any] | None:
        """获取单个备份的详细信息

        Args:
            backup_name: 备份名称（如 "backup_20260530_120000"）

        Returns:
            备份信息字典，不存在时返回 None
        """
        # 先查 meta
        meta_path = self._backup_dir / f"{backup_name}_meta.json"
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                return json.load(f)

        # 再查归档
        archive_path = self._backup_dir / f"{backup_name}.tar.gz"
        if archive_path.exists():
            return {
                "name": backup_name,
                "path": str(archive_path),
                "size_bytes": archive_path.stat().st_size,
            }

        return None

    def restore_backup(
        self,
        backup_name: str,
        restore_data: bool = True,
        restore_configs: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """从备份恢复

        Args:
            backup_name: 备份名称
            restore_data: 是否恢复 data/ 目录
            restore_configs: 是否恢复 configs/ 目录
            dry_run: 试运行模式，只检查不实际恢复

        Returns:
            恢复结果字典
        """
        archive_path = self._backup_dir / f"{backup_name}.tar.gz"
        if not archive_path.exists():
            # 尝试在 backup_dir 中查找
            alt_path = self._backup_dir / backup_name
            if alt_path.exists() and alt_path.is_dir():
                return self._restore_from_dir(
                    alt_path, restore_data, restore_configs, dry_run
                )
            return {"error": f"备份 '{backup_name}' 不存在", "success": False}

        restored_files: list[str] = []
        errors: list[str] = []

        if dry_run:
            # 试运行模式：列出将被恢复的文件
            with tarfile.open(str(archive_path), "r:gz") as tar:
                for member in tar.getmembers():
                    name = member.name
                    if name == "backup_meta.json":
                        continue
                    if restore_data and name.startswith("data/"):
                        restored_files.append(name)
                    elif restore_configs and name.startswith("configs/"):
                        restored_files.append(name)
            return {
                "success": True,
                "dry_run": True,
                "would_restore": restored_files,
                "file_count": len(restored_files),
            }

        # 实际恢复
        with tarfile.open(str(archive_path), "r:gz") as tar:
            for member in tar.getmembers():
                name = member.name
                if name == "backup_meta.json":
                    continue

                # 过滤要恢复的目录
                should_restore = False
                if restore_data and name.startswith("data/"):
                    should_restore = True
                elif restore_configs and name.startswith("configs/"):
                    should_restore = True

                if not should_restore:
                    continue

                target_path = self._base_dir / name

                # 安全检查：路径遍历
                try:
                    target_path.resolve().relative_to(self._base_dir.resolve())
                except ValueError:
                    errors.append(f"不安全的路径: {name}")
                    continue

                if member.isdir():
                    target_path.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        src_file = tar.extractfile(member)
                        if src_file:
                            with open(target_path, "wb") as f:
                                shutil.copyfileobj(src_file, f)
                            restored_files.append(name)
                    except Exception as e:
                        errors.append(f"恢复失败 {name}: {e}")

        result: dict[str, Any] = {
            "success": True,
            "backup_name": backup_name,
            "restored_files": len(restored_files),
            "errors": errors,
        }

        logger.info(
            "backup_restored",
            name=backup_name,
            file_count=len(restored_files),
            error_count=len(errors),
        )

        return result

    def delete_backup(self, backup_name: str) -> bool:
        """删除备份

        Args:
            backup_name: 备份名称

        Returns:
            是否删除成功
        """
        deleted = False

        archive_path = self._backup_dir / f"{backup_name}.tar.gz"
        if archive_path.exists():
            archive_path.unlink()
            deleted = True

        meta_path = self._backup_dir / f"{backup_name}_meta.json"
        if meta_path.exists():
            meta_path.unlink()
            deleted = True

        if deleted:
            logger.info("backup_deleted", name=backup_name)

        return deleted

    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """清理旧备份，只保留最近的 N 个

        Args:
            keep_count: 保留的备份数量

        Returns:
            删除的备份数量
        """
        backups = self.list_backups()
        if len(backups) <= keep_count:
            return 0

        to_delete = backups[keep_count:]
        deleted_count = 0

        for backup in to_delete:
            name = backup.get("name", "")
            if name and self.delete_backup(name):
                deleted_count += 1

        logger.info("backup_cleanup", deleted=deleted_count, kept=keep_count)
        return deleted_count

    def _restore_from_dir(
        self,
        dir_path: Path,
        restore_data: bool,
        restore_configs: bool,
        dry_run: bool,
    ) -> dict[str, Any]:
        """从已解压的备份目录恢复"""
        restored_files: list[str] = []

        for source_dir_name in (["data"] if restore_data else []) + (
            ["configs"] if restore_configs else []
        ):
            source_dir = dir_path / source_dir_name
            if not source_dir.exists():
                continue

            target_dir = self._base_dir / source_dir_name
            if dry_run:
                restored_files.extend(
                    str(f.relative_to(dir_path))
                    for f in source_dir.rglob("*")
                    if f.is_file()
                )
                continue

            # 实际恢复
            if target_dir.exists():
                shutil.rmtree(str(target_dir))
            shutil.copytree(str(source_dir), str(target_dir))

            restored_files.extend(
                str(f.relative_to(dir_path))
                for f in source_dir.rglob("*")
                if f.is_file()
            )

        return {
            "success": True,
            "dry_run": dry_run,
            "restored_files": len(restored_files),
            "files": restored_files if dry_run else [],
        }
