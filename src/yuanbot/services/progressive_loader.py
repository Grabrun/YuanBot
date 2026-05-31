"""三层渐进式动态加载策略

实现 capability-tool-system.md 第6节的三层加载架构：
- 阶段一 (启动时): 元数据索引 — 仅存 id/name/tags/token_cost，不进入 LLM 上下文
- 阶段二 (匹配时): 定义注入 — 加载 prompt_template / Function Calling Schema
- 阶段三 (执行时): 资源获取 — LRU 缓存按需获取额外资源

整体效果：即使系统安装了上百个 Skills/Tools，每个会话初始只增加约 50 tokens
的索引开销，注入定义后仅增加 500-1500 tokens。
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import structlog

from yuanbot.services.domain_matcher import DomainMatcher, DomainMatchResult
from yuanbot.skills.manager import SkillManager
from yuanbot.tools.manager import ToolManager

logger = structlog.get_logger(__name__)


@dataclass
class MetadataIndex:
    """阶段一：元数据索引条目"""

    item_id: str
    item_type: str  # "skill" or "tool"
    name: str
    category: str
    capability_tags: list[str]
    token_cost_estimate: int
    enabled: bool = True


@dataclass
class LoadingStats:
    """加载统计"""

    stage1_index_count: int = 0  # 元数据索引数量
    stage2_skills_loaded: int = 0  # 阶段二加载的 Skill 数量
    stage2_tools_loaded: int = 0  # 阶段二加载的 Tool 数量
    stage2_tokens_estimate: int = 0  # 阶段二注入的 token 估算
    stage3_cache_hits: int = 0  # 阶段三缓存命中次数
    stage3_cache_misses: int = 0  # 阶段三缓存未命中次数
    total_load_time_ms: float = 0.0


class LRUCache:
    """简单的 LRU 缓存，用于阶段三资源获取"""

    def __init__(self, max_size: int = 100):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def put(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def size(self) -> int:
        return len(self._cache)


class ProgressiveLoader:
    """三层渐进式动态加载器

    管理 Skills/Tools 的分层加载策略，最大限度减少 Token 消耗。

    使用方式::

        loader = ProgressiveLoader(
            skill_manager=skill_manager,
            tool_manager=tool_manager,
            domain_matcher=domain_matcher,
        )

        # 启动时：构建元数据索引
        await loader.build_index()

        # 匹配时：根据上下文注入定义
        loaded = await loader.load_for_context(
            intent="想听故事",
            emotion="",
            capability_domains=["creative_storytelling"],
        )

        # 执行时：按需获取资源
        resource = await loader.get_resource("skill", "bedtime_story", resource_key="prompts_zh")
    """

    def __init__(
        self,
        skill_manager: SkillManager,
        tool_manager: ToolManager,
        domain_matcher: DomainMatcher | None = None,
        resource_cache_size: int = 100,
    ):
        self._skills = skill_manager
        self._tools = tool_manager
        self._domain_matcher = domain_matcher or DomainMatcher()
        self._index: list[MetadataIndex] = []
        self._resource_cache = LRUCache(max_size=resource_cache_size)
        self._stats = LoadingStats()

    async def build_index(self) -> None:
        """阶段一：构建元数据索引

        启动时扫描所有已启用的 Skills/Tools，建立轻量级索引。
        索引仅包含 id、name、tags、token_cost 等元数据，不加载完整定义。
        """
        start_time = time.monotonic()
        self._index.clear()

        # 索引 Skills
        for skill_info in self._skills.get_all_skills():
            if not skill_info.get("enabled", True):
                continue
            self._index.append(
                MetadataIndex(
                    item_id=skill_info["skill_id"],
                    item_type="skill",
                    name=skill_info.get("name", ""),
                    category=skill_info.get("category", ""),
                    capability_tags=skill_info.get("capability_tags", []),
                    token_cost_estimate=skill_info.get("token_cost_estimate", 200),
                )
            )

        # 索引 Tools
        for tool_info in self._tools.get_all_tools():
            if not tool_info.get("enabled", True):
                continue
            self._index.append(
                MetadataIndex(
                    item_id=tool_info["tool_id"],
                    item_type="tool",
                    name=tool_info.get("name", ""),
                    category=tool_info.get("category", ""),
                    capability_tags=[],
                    token_cost_estimate=100,  # Tool schema 通常较短
                )
            )

        self._stats.stage1_index_count = len(self._index)
        elapsed_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "progressive_index_built",
            index_count=len(self._index),
            elapsed_ms=f"{elapsed_ms:.1f}",
        )

    async def load_for_context(
        self,
        intent: str = "",
        emotion: str = "",
        capability_domains: list[str] | None = None,
        max_skills: int = 2,
        max_tools: int = 3,
    ) -> ProgressiveLoadResult:
        """阶段二：根据上下文加载匹配的 Skill/Tool 定义

        通过 DomainMatcher 匹配能力域，然后加载对应的完整定义。

        Args:
            intent: 用户意图
            emotion: 情感标签
            capability_domains: 人设能力域声明
            max_skills: 最多加载的 Skill 数量
            max_tools: 最多加载的 Tool 数量

        Returns:
            ProgressiveLoadResult: 加载结果
        """
        start_time = time.monotonic()

        # 1. 能力域匹配
        match_result = self._domain_matcher.match(
            intent=intent,
            emotion=emotion,
            capability_domains=capability_domains,
        )

        # 2. 从索引中筛选匹配的 Skills/Tools
        matched_skills: list[MetadataIndex] = []
        matched_tools: list[MetadataIndex] = []

        for entry in self._index:
            if not entry.enabled:
                continue

            # 检查是否匹配任一能力域
            is_match = False
            for domain in match_result.matched_domains:
                if entry.category == domain.value or domain.value in entry.capability_tags:
                    is_match = True
                    break
                # 也检查标签与意图的直接匹配
                for tag in entry.capability_tags:
                    if tag in intent:
                        is_match = True
                        break

            if is_match:
                if entry.item_type == "skill":
                    matched_skills.append(entry)
                else:
                    matched_tools.append(entry)

        # 3. 按 token_cost 排序（优先加载低成本的）
        matched_skills.sort(key=lambda x: x.token_cost_estimate)
        matched_tools.sort(key=lambda x: x.token_cost_estimate)

        # 4. 截取到上限
        selected_skills = matched_skills[:max_skills]
        selected_tools = matched_tools[:max_tools]

        # 5. 加载完整定义
        loaded_skill_prompts: dict[str, str] = {}
        loaded_tool_schemas: dict[str, dict] = {}
        total_tokens = 0

        for entry in selected_skills:
            prompt = self._skills.get_skill_prompt(entry.item_id)
            if prompt:
                loaded_skill_prompts[entry.item_id] = prompt
                total_tokens += entry.token_cost_estimate

        for entry in selected_tools:
            schema = self._tools.get_tool_schema(entry.item_id)
            if schema:
                loaded_tool_schemas[entry.item_id] = schema
                total_tokens += entry.token_cost_estimate

        # 更新统计
        elapsed_ms = (time.monotonic() - start_time) * 1000
        self._stats.stage2_skills_loaded = len(loaded_skill_prompts)
        self._stats.stage2_tools_loaded = len(loaded_tool_schemas)
        self._stats.stage2_tokens_estimate = total_tokens
        self._stats.total_load_time_ms += elapsed_ms

        logger.info(
            "progressive_load_completed",
            skills_loaded=len(loaded_skill_prompts),
            tools_loaded=len(loaded_tool_schemas),
            tokens_estimate=total_tokens,
            elapsed_ms=f"{elapsed_ms:.1f}",
        )

        return ProgressiveLoadResult(
            match_result=match_result,
            skill_prompts=loaded_skill_prompts,
            tool_schemas=loaded_tool_schemas,
            tokens_estimate=total_tokens,
            load_time_ms=elapsed_ms,
        )

    async def get_resource(
        self,
        item_type: str,
        item_id: str,
        resource_key: str = "default",
    ) -> Any | None:
        """阶段三：按需获取执行时资源

        使用 LRU 缓存管理资源，避免重复加载。

        Args:
            item_type: "skill" or "tool"
            item_id: Skill/Tool ID
            resource_key: 资源键名

        Returns:
            资源内容，或 None
        """
        cache_key = f"{item_type}:{item_id}:{resource_key}"

        # 尝试从缓存获取
        cached = self._resource_cache.get(cache_key)
        if cached is not None:
            self._stats.stage3_cache_hits += 1
            return cached

        self._stats.stage3_cache_misses += 1

        # 缓存未命中，返回 None（实际资源获取由具体 Manager 实现）
        logger.debug(
            "progressive_resource_miss",
            item_type=item_type,
            item_id=item_id,
            resource_key=resource_key,
        )
        return None

    def get_index_summary(self) -> dict[str, Any]:
        """获取索引摘要（用于调试和监控）"""
        skills = [e for e in self._index if e.item_type == "skill"]
        tools = [e for e in self._index if e.item_type == "tool"]
        return {
            "total_entries": len(self._index),
            "skills": len(skills),
            "tools": len(tools),
            "categories": list({e.category for e in self._index if e.category}),
            "stats": {
                "stage1_index_count": self._stats.stage1_index_count,
                "stage2_skills_loaded": self._stats.stage2_skills_loaded,
                "stage2_tools_loaded": self._stats.stage2_tools_loaded,
                "stage2_tokens_estimate": self._stats.stage2_tokens_estimate,
                "stage3_cache_hits": self._stats.stage3_cache_hits,
                "stage3_cache_misses": self._stats.stage3_cache_misses,
                "resource_cache_size": self._resource_cache.size,
            },
        }


@dataclass
class ProgressiveLoadResult:
    """阶段二加载结果"""

    match_result: DomainMatchResult
    skill_prompts: dict[str, str] = field(default_factory=dict)  # skill_id -> prompt
    tool_schemas: dict[str, dict] = field(default_factory=dict)  # tool_id -> schema
    tokens_estimate: int = 0
    load_time_ms: float = 0.0

    @property
    def skill_ids(self) -> list[str]:
        return list(self.skill_prompts.keys())

    @property
    def tool_ids(self) -> list[str]:
        return list(self.tool_schemas.keys())
