"""向量存储实现

支持 Milvus Lite（首选，嵌入式）和内存向量存储（回退方案）。
提供统一接口：add_vector, search_similar, delete_vector。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 检测 pymilvus 是否可用
try:
    from pymilvus import MilvusClient

    _HAS_MILVUS = True
except ImportError:
    _HAS_MILVUS = False


def is_milvus_available() -> bool:
    """检测 pymilvus 是否已安装"""
    return _HAS_MILVUS


@dataclass
class VectorEntry:
    """向量条目"""

    id: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore:
    """向量存储统一接口

    首选 Milvus Lite（嵌入式），回退到内存向量存储。
    支持自动检测 pymilvus 可用性。
    """

    COLLECTION_NAME = "yuanbot_vectors"
    DEFAULT_DIMENSION = 1536

    def __init__(
        self,
        use_milvus: bool | None = None,
        milvus_uri: str | None = None,
        dimension: int = DEFAULT_DIMENSION,
    ):
        # use_milvus=None 时自动检测
        if use_milvus is None:
            self._use_milvus = _HAS_MILVUS
        else:
            self._use_milvus = use_milvus and _HAS_MILVUS
        self._milvus_uri = milvus_uri or "data/yuanbot_vectors.db"
        self._dimension = dimension
        self._milvus_client: Any = None
        self._memory_store: InMemoryVectorStore | None = None
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def backend(self) -> str:
        """当前使用的后端名称"""
        if self._milvus_client is not None:
            return "milvus_lite"
        if self._memory_store is not None:
            return "memory"
        return "uninitialized"

    async def initialize(self) -> None:
        """初始化向量存储"""
        if self._initialized:
            return

        if self._use_milvus:
            try:
                await self._init_milvus()
                self._initialized = True
                logger.info(
                    "vector_store_initialized",
                    backend="milvus_lite",
                    uri=self._milvus_uri,
                    dimension=self._dimension,
                )
                return
            except Exception as e:
                logger.warning(
                    "milvus_init_failed_fallback_memory",
                    error=str(e),
                )

        # 回退到内存存储
        self._memory_store = InMemoryVectorStore()
        self._initialized = True
        logger.info("vector_store_initialized", backend="memory")

    async def close(self) -> None:
        """关闭向量存储"""
        if self._milvus_client:
            try:
                self._milvus_client.close()
            except Exception:
                pass
            self._milvus_client = None
        self._memory_store = None
        self._initialized = False
        logger.info("vector_store_closed")

    async def _init_milvus(self) -> None:
        """初始化 Milvus Lite

        使用 pymilvus.MilvusClient 创建嵌入式向量数据库实例。
        Milvus Lite 将数据持久化到本地文件。
        """
        if not _HAS_MILVUS:
            raise ImportError(
                "pymilvus is required for Milvus vector store. "
                "Install it with: pip install pymilvus"
            )

        uri = self._milvus_uri
        self._milvus_client = MilvusClient(uri=uri)

        # 创建集合（如果不存在）
        if not self._milvus_client.has_collection(self.COLLECTION_NAME):
            self._milvus_client.create_collection(
                collection_name=self.COLLECTION_NAME,
                dimension=self._dimension,
            )
            logger.info(
                "milvus_collection_created",
                collection=self.COLLECTION_NAME,
                dimension=self._dimension,
            )

    async def add_vector(
        self,
        id: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """添加向量"""
        if not self._initialized:
            await self.initialize()

        if self._milvus_client:
            await self._add_vector_milvus(id, vector, metadata)
        elif self._memory_store:
            self._memory_store.add_vector(id, vector, metadata)

    async def search_similar(
        self,
        query_vector: list[float],
        top_k: int = 5,
        threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """搜索相似向量"""
        if not self._initialized:
            await self.initialize()

        if self._milvus_client:
            return await self._search_milvus(query_vector, top_k, threshold)
        elif self._memory_store:
            return self._memory_store.search_similar(query_vector, top_k, threshold)
        return []

    async def delete_vector(self, id: str) -> None:
        """删除向量"""
        if not self._initialized:
            await self.initialize()

        if self._milvus_client:
            await self._delete_milvus(id)
        elif self._memory_store:
            self._memory_store.delete_vector(id)

    async def _add_vector_milvus(
        self,
        id: str,
        vector: list[float],
        metadata: dict[str, Any] | None,
    ) -> None:
        """通过 Milvus 添加向量"""
        try:
            data = {
                "id": id,
                "vector": vector,
                **(metadata or {}),
            }
            self._milvus_client.insert(
                collection_name=self.COLLECTION_NAME,
                data=[data],
            )
        except Exception as e:
            logger.error("milvus_add_vector_failed", id=id, error=str(e))
            raise

    async def _search_milvus(
        self,
        query_vector: list[float],
        top_k: int,
        threshold: float,
    ) -> list[dict[str, Any]]:
        """通过 Milvus 搜索"""
        try:
            results = self._milvus_client.search(
                collection_name=self.COLLECTION_NAME,
                data=[query_vector],
                limit=top_k,
                output_fields=["*"],
            )
            formatted = []
            for hits in results:
                for hit in hits:
                    score = hit.get("distance", 0.0)
                    if score >= threshold:
                        formatted.append(
                            {
                                "id": hit.get("id", ""),
                                "score": score,
                                "metadata": {
                                    k: v
                                    for k, v in hit.items()
                                    if k not in ("id", "vector", "distance")
                                },
                            }
                        )
            return formatted
        except Exception as e:
            logger.error("milvus_search_failed", error=str(e))
            return []

    async def _delete_milvus(self, id: str) -> None:
        """通过 Milvus 删除"""
        try:
            self._milvus_client.delete(
                collection_name=self.COLLECTION_NAME,
                ids=[id],
            )
        except Exception as e:
            logger.error("milvus_delete_failed", id=id, error=str(e))


class InMemoryVectorStore:
    """内存向量存储（回退方案）

    使用余弦相似度进行搜索，适用于开发和测试环境。
    """

    def __init__(self):
        self._vectors: dict[str, VectorEntry] = {}

    def add_vector(
        self,
        id: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """添加向量"""
        self._vectors[id] = VectorEntry(
            id=id,
            vector=vector,
            metadata=metadata or {},
        )

    def search_similar(
        self,
        query_vector: list[float],
        top_k: int = 5,
        threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """搜索相似向量（余弦相似度）"""
        results: list[dict[str, Any]] = []

        for entry in self._vectors.values():
            score = self._cosine_similarity(query_vector, entry.vector)
            if score >= threshold:
                results.append(
                    {
                        "id": entry.id,
                        "score": score,
                        "metadata": entry.metadata,
                    }
                )

        # 按分数降序排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def delete_vector(self, id: str) -> None:
        """删除向量"""
        self._vectors.pop(id, None)

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """计算余弦相似度"""
        if len(a) != len(b):
            return 0.0
        dot_product = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)
