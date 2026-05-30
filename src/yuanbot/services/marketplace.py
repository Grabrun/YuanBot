"""YuanBot 社区扩展市场客户端

提供扩展搜索、发现、安装功能：
- 从远端注册表搜索扩展
- 获取扩展详情和版本信息
- 下载并安装扩展到本地
- 支持本地缓存和离线模式

注册表格式: JSON index.json 文件，包含扩展列表

设计参考: development-standards-ecosystem.md
"""

from __future__ import annotations

import json
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 默认注册表 URL（可通过配置覆盖）
DEFAULT_REGISTRY_URL = "https://registry.yuanbot.app"
FALLBACK_REGISTRY_URL = "https://raw.githubusercontent.com/yuanbot-ai/extensions/main"

# 缓存配置
CACHE_DIR = Path("data/.marketplace_cache")
CACHE_TTL_SECONDS = 3600  # 1 小时


@dataclass
class ExtensionEntry:
    """市场扩展条目"""

    id: str
    name: str
    description: str = ""
    version: str = "0.0.0"
    author: str = ""
    type: str = ""  # ai_provider, channel, skill, tool, persona, trigger
    license: str = ""
    download_url: str = ""
    homepage: str = ""
    repository: str = ""
    keywords: list[str] = field(default_factory=list)
    downloads: int = 0
    stars: int = 0
    min_core_version: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "type": self.type,
            "license": self.license,
            "download_url": self.download_url,
            "homepage": self.homepage,
            "repository": self.repository,
            "keywords": self.keywords,
            "downloads": self.downloads,
            "stars": self.stars,
            "min_core_version": self.min_core_version,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtensionEntry:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "0.0.0"),
            author=data.get("author", ""),
            type=data.get("type", ""),
            license=data.get("license", ""),
            download_url=data.get("download_url", ""),
            homepage=data.get("homepage", ""),
            repository=data.get("repository", ""),
            keywords=data.get("keywords", []),
            downloads=data.get("downloads", 0),
            stars=data.get("stars", 0),
            min_core_version=data.get("min_core_version", ""),
            updated_at=data.get("updated_at", ""),
        )


class MarketplaceClient:
    """社区扩展市场客户端

    从远端注册表获取扩展索引，支持搜索和下载。
    自动缓存索引文件以减少网络请求。
    """

    def __init__(
        self,
        registry_url: str | None = None,
        cache_dir: Path | str | None = None,
    ) -> None:
        self._registry_url = registry_url or DEFAULT_REGISTRY_URL
        self._cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._index: list[ExtensionEntry] | None = None
        self._index_loaded_at: float = 0

    @property
    def registry_url(self) -> str:
        return self._registry_url

    async def search(
        self,
        query: str = "",
        ext_type: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """搜索扩展

        Args:
            query: 搜索关键词（匹配 name, description, keywords）
            ext_type: 过滤扩展类型
            limit: 返回数量限制
            offset: 分页偏移

        Returns:
            { "extensions": [...], "total": N, "offset": N, "limit": N }
        """
        index = await self._load_index()
        results = list(index)

        # 关键词过滤
        if query:
            q_lower = query.lower()
            results = [
                e
                for e in results
                if q_lower in e.name.lower()
                or q_lower in e.description.lower()
                or q_lower in e.id.lower()
                or any(q_lower in kw.lower() for kw in e.keywords)
            ]

        # 类型过滤
        if ext_type:
            results = [e for e in results if e.type == ext_type]

        total = len(results)
        page = results[offset : offset + limit]

        return {
            "extensions": [e.to_dict() for e in page],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    async def get_extension(self, ext_id: str) -> ExtensionEntry | None:
        """获取单个扩展详情

        Args:
            ext_id: 扩展 ID

        Returns:
            ExtensionEntry 或 None
        """
        index = await self._load_index()
        for entry in index:
            if entry.id == ext_id:
                return entry
        return None

    async def list_extensions(
        self,
        ext_type: str = "",
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "downloads",
    ) -> dict[str, Any]:
        """列出扩展

        Args:
            ext_type: 过滤扩展类型
            limit: 返回数量
            offset: 分页偏移
            sort_by: 排序方式 (downloads, stars, updated_at, name)

        Returns:
            { "extensions": [...], "total": N }
        """
        index = await self._load_index()
        results = list(index)

        if ext_type:
            results = [e for e in results if e.type == ext_type]

        # 排序
        if sort_by == "downloads":
            results.sort(key=lambda e: e.downloads, reverse=True)
        elif sort_by == "stars":
            results.sort(key=lambda e: e.stars, reverse=True)
        elif sort_by == "updated_at":
            results.sort(key=lambda e: e.updated_at, reverse=True)
        elif sort_by == "name":
            results.sort(key=lambda e: e.name.lower())

        total = len(results)
        page = results[offset : offset + limit]

        return {
            "extensions": [e.to_dict() for e in page],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    async def download_extension(
        self,
        ext_id: str,
        dest_dir: Path | str,
        version: str = "",
    ) -> Path | None:
        """下载并解压扩展到目标目录

        Args:
            ext_id: 扩展 ID
            dest_dir: 目标目录
            version: 指定版本（默认最新）

        Returns:
            解压后的扩展路径，失败返回 None
        """
        entry = await self.get_extension(ext_id)
        if not entry:
            logger.error("marketplace_extension_not_found", ext_id=ext_id)
            return None

        if not entry.download_url:
            logger.error("marketplace_no_download_url", ext_id=ext_id)
            return None

        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)

        try:
            import httpx

            # 下载到临时文件
            tmp_zip = dest / f".tmp_{ext_id}.zip"
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                resp = await client.get(entry.download_url)
                resp.raise_for_status()
                tmp_zip.write_bytes(resp.content)

            # 解压
            ext_dest = dest / ext_id
            if ext_dest.exists():
                import shutil

                shutil.rmtree(ext_dest)

            with zipfile.ZipFile(tmp_zip) as zf:
                zf.extractall(ext_dest)

            # 清理临时文件
            tmp_zip.unlink(missing_ok=True)

            # 验证 manifest.json 存在
            manifest_path = ext_dest / "manifest.json"
            if not manifest_path.exists():
                # 尝试在子目录中查找
                for sub in ext_dest.iterdir():
                    if sub.is_dir() and (sub / "manifest.json").exists():
                        # 移动内容到 ext_dest
                        import shutil

                        for item in sub.iterdir():
                            shutil.move(str(item), str(ext_dest / item.name))
                        sub.rmdir()
                        break

            logger.info(
                "marketplace_extension_downloaded",
                ext_id=ext_id,
                version=entry.version,
                dest=str(ext_dest),
            )

            return ext_dest

        except Exception as e:
            logger.error(
                "marketplace_download_failed",
                ext_id=ext_id,
                error=str(e),
            )
            return None

    async def get_categories(self) -> dict[str, int]:
        """获取扩展分类统计

        Returns:
            { "skill": 12, "tool": 8, ... }
        """
        index = await self._load_index()
        categories: dict[str, int] = {}
        for entry in index:
            categories[entry.type] = categories.get(entry.type, 0) + 1
        return categories

    async def refresh_index(self) -> bool:
        """强制刷新注册表索引

        Returns:
            是否刷新成功
        """
        return await self._fetch_index()

    async def _load_index(self) -> list[ExtensionEntry]:
        """加载注册表索引（带缓存）"""
        now = time.time()

        # 内存缓存有效
        if self._index and (now - self._index_loaded_at) < CACHE_TTL_SECONDS:
            return self._index

        # 磁盘缓存
        cache_file = self._cache_dir / "index.json"
        if cache_file.exists():
            cache_age = now - cache_file.stat().st_mtime
            if cache_age < CACHE_TTL_SECONDS:
                try:
                    data = json.loads(cache_file.read_text(encoding="utf-8"))
                    self._index = [ExtensionEntry.from_dict(e) for e in data]
                    self._index_loaded_at = now
                    return self._index
                except Exception:
                    pass

        # 从远端拉取
        if await self._fetch_index():
            return self._index or []

        # 降级到磁盘缓存（即使过期）
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                self._index = [ExtensionEntry.from_dict(e) for e in data]
                return self._index
            except Exception:
                pass

        return []

    async def _fetch_index(self) -> bool:
        """从远端注册表拉取索引"""
        try:
            import httpx

            index_url = f"{self._registry_url}/index.json"
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(index_url)
                resp.raise_for_status()
                data = resp.json()

            # 缓存到磁盘
            cache_file = self._cache_dir / "index.json"
            cache_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            self._index = [ExtensionEntry.from_dict(e) for e in data]
            self._index_loaded_at = time.time()

            logger.info(
                "marketplace_index_loaded",
                count=len(self._index),
                source=self._registry_url,
            )
            return True

        except Exception as e:
            logger.warning("marketplace_index_fetch_failed", error=str(e))
            return False

    def _load_local_index(self) -> list[ExtensionEntry]:
        """加载本地内置扩展列表（作为注册表不可用时的降级方案）

        扫描 configs/Plugins/ 目录下的 YAML 文件。
        """
        entries: list[ExtensionEntry] = []

        # 扫描内置 skills
        skills_dir = Path("configs/Plugins/skills")
        if skills_dir.exists():
            import yaml

            for yaml_file in sorted(skills_dir.glob("*.yaml")):
                try:
                    with open(yaml_file) as f:
                        data = yaml.safe_load(f) or {}
                    entries.append(
                        ExtensionEntry(
                            id=f"builtin-skill-{yaml_file.stem}",
                            name=data.get("name", yaml_file.stem),
                            description=data.get("description", ""),
                            version="1.0.0",
                            author="YuanBot",
                            type="skill",
                            keywords=data.get("keywords", []),
                        )
                    )
                except Exception:
                    continue

        # 扫描内置 tools
        tools_dir = Path("configs/Plugins/tools")
        if tools_dir.exists():
            import yaml

            for yaml_file in sorted(tools_dir.glob("*.yaml")):
                try:
                    with open(yaml_file) as f:
                        data = yaml.safe_load(f) or {}
                    entries.append(
                        ExtensionEntry(
                            id=f"builtin-tool-{yaml_file.stem}",
                            name=data.get("name", yaml_file.stem),
                            description=data.get("description", ""),
                            version="1.0.0",
                            author="YuanBot",
                            type="tool",
                            keywords=data.get("keywords", []),
                        )
                    )
                except Exception:
                    continue

        return entries
