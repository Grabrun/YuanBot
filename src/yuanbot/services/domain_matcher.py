"""能力域匹配器 (Domain Matcher)

将意图、情感、人设能力域声明映射到具体的 Skills 和 Tools。

设计参考: capability-tool-system.md 第8节 能力域匹配与决策流程

预定义能力域:
- emotional_care: 情绪安抚、共情、心理支持
- daily_chat: 日常闲聊、天气、新闻
- creative_storytelling: 故事生成、角色扮演、文字游戏
- task_management: 提醒、日程、清单
- knowledge_query: 联网搜索、知识问答
- media_generation: 图片、音频、视频生成
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class CapabilityDomain(Enum):
    """预定义能力域"""

    EMOTIONAL_CARE = "emotional_care"
    DAILY_CHAT = "daily_chat"
    CREATIVE_STORYTELLING = "creative_storytelling"
    TASK_MANAGEMENT = "task_management"
    KNOWLEDGE_QUERY = "knowledge_query"
    MEDIA_GENERATION = "media_generation"


# 意图关键词 → 能力域映射表
INTENT_DOMAIN_MAP: dict[str, list[CapabilityDomain]] = {
    # 情绪相关
    "难过": [CapabilityDomain.EMOTIONAL_CARE],
    "伤心": [CapabilityDomain.EMOTIONAL_CARE],
    "焦虑": [CapabilityDomain.EMOTIONAL_CARE],
    "害怕": [CapabilityDomain.EMOTIONAL_CARE],
    "愤怒": [CapabilityDomain.EMOTIONAL_CARE],
    "压力": [CapabilityDomain.EMOTIONAL_CARE],
    "孤独": [CapabilityDomain.EMOTIONAL_CARE],
    "安慰": [CapabilityDomain.EMOTIONAL_CARE],
    "哭": [CapabilityDomain.EMOTIONAL_CARE],
    # 日常聊天
    "天气": [CapabilityDomain.DAILY_CHAT, CapabilityDomain.KNOWLEDGE_QUERY],
    "新闻": [CapabilityDomain.DAILY_CHAT, CapabilityDomain.KNOWLEDGE_QUERY],
    "今天": [CapabilityDomain.DAILY_CHAT],
    "吃": [CapabilityDomain.DAILY_CHAT],
    "玩": [CapabilityDomain.DAILY_CHAT],
    "聊天": [CapabilityDomain.DAILY_CHAT],
    "你好": [CapabilityDomain.DAILY_CHAT],
    # 创意故事
    "故事": [CapabilityDomain.CREATIVE_STORYTELLING],
    "讲个": [CapabilityDomain.CREATIVE_STORYTELLING],
    "童话": [CapabilityDomain.CREATIVE_STORYTELLING],
    "冒险": [CapabilityDomain.CREATIVE_STORYTELLING],
    "角色": [CapabilityDomain.CREATIVE_STORYTELLING],
    "想象": [CapabilityDomain.CREATIVE_STORYTELLING],
    "睡前": [CapabilityDomain.CREATIVE_STORYTELLING],
    # 任务管理
    "提醒": [CapabilityDomain.TASK_MANAGEMENT],
    "日程": [CapabilityDomain.TASK_MANAGEMENT],
    "清单": [CapabilityDomain.TASK_MANAGEMENT],
    "待办": [CapabilityDomain.TASK_MANAGEMENT],
    "闹钟": [CapabilityDomain.TASK_MANAGEMENT],
    "记一下": [CapabilityDomain.TASK_MANAGEMENT],
    # 知识查询
    "搜索": [CapabilityDomain.KNOWLEDGE_QUERY],
    "查询": [CapabilityDomain.KNOWLEDGE_QUERY],
    "什么是": [CapabilityDomain.KNOWLEDGE_QUERY],
    "为什么": [CapabilityDomain.KNOWLEDGE_QUERY],
    "怎么": [CapabilityDomain.KNOWLEDGE_QUERY],
    "帮我查": [CapabilityDomain.KNOWLEDGE_QUERY],
}

# 情感标签 → 能力域映射
EMOTION_DOMAIN_MAP: dict[str, list[CapabilityDomain]] = {
    "sadness": [CapabilityDomain.EMOTIONAL_CARE],
    "anger": [CapabilityDomain.EMOTIONAL_CARE],
    "fear": [CapabilityDomain.EMOTIONAL_CARE],
    "anxiety": [CapabilityDomain.EMOTIONAL_CARE],
    "loneliness": [CapabilityDomain.EMOTIONAL_CARE],
    "joy": [CapabilityDomain.DAILY_CHAT],
    "surprise": [CapabilityDomain.DAILY_CHAT],
    "neutral": [CapabilityDomain.DAILY_CHAT],
}

# 能力域 → 默认 token 预算上限
DOMAIN_TOKEN_BUDGETS: dict[CapabilityDomain, int] = {
    CapabilityDomain.EMOTIONAL_CARE: 500,
    CapabilityDomain.DAILY_CHAT: 300,
    CapabilityDomain.CREATIVE_STORYTELLING: 800,
    CapabilityDomain.TASK_MANAGEMENT: 200,
    CapabilityDomain.KNOWLEDGE_QUERY: 400,
    CapabilityDomain.MEDIA_GENERATION: 300,
}


@dataclass
class DomainMatchResult:
    """能力域匹配结果"""

    matched_domains: list[CapabilityDomain] = field(default_factory=list)
    intent_scores: dict[str, float] = field(default_factory=dict)  # domain -> score
    emotion_scores: dict[str, float] = field(default_factory=dict)
    combined_scores: dict[str, float] = field(default_factory=dict)  # domain -> combined score
    recommended_skill_count: int = 2  # 推荐加载的 Skill 数量
    recommended_tool_count: int = 3  # 推荐加载的 Tool 数量


class DomainMatcher:
    """能力域匹配器

    根据意图、情感和人设能力域声明，计算各能力域的匹配分数，
    用于指导 Skill/Tool 的动态加载。

    匹配策略（权重）:
    - 人设能力域声明: 3 分（最高优先级）
    - 意图关键词匹配: 2 分
    - 情感标签匹配: 1 分

    设计参考: capability-tool-system.md 第8节
    """

    # 权重配置
    WEIGHT_DOMAIN_DECLARATION = 3.0
    WEIGHT_INTENT = 2.0
    WEIGHT_EMOTION = 1.0

    def __init__(
        self,
        intent_domain_map: dict[str, list[CapabilityDomain]] | None = None,
        emotion_domain_map: dict[str, list[CapabilityDomain]] | None = None,
    ):
        self._intent_map = intent_domain_map or INTENT_DOMAIN_MAP
        self._emotion_map = emotion_domain_map or EMOTION_DOMAIN_MAP

    def match(
        self,
        intent: str = "",
        emotion: str = "",
        capability_domains: list[str] | None = None,
        max_skills: int = 2,
        max_tools: int = 3,
    ) -> DomainMatchResult:
        """执行能力域匹配

        Args:
            intent: 用户意图文本
            emotion: 情感标签
            capability_domains: 人设声明的能力域列表
            max_skills: 推荐加载的 Skill 数量上限
            max_tools: 推荐加载的 Tool 数量上限

        Returns:
            DomainMatchResult: 匹配结果
        """
        scores: dict[str, float] = {}
        result = DomainMatchResult(
            recommended_skill_count=max_skills,
            recommended_tool_count=max_tools,
        )

        # 1. 人设能力域声明（最高权重）
        declared_domains = capability_domains or []
        for domain_str in declared_domains:
            try:
                domain = CapabilityDomain(domain_str)
                scores[domain_str] = scores.get(domain_str, 0) + self.WEIGHT_DOMAIN_DECLARATION
                if domain not in result.matched_domains:
                    result.matched_domains.append(domain)
            except ValueError:
                # 非预定义能力域，仍然给予高分
                scores[domain_str] = scores.get(domain_str, 0) + self.WEIGHT_DOMAIN_DECLARATION

        # 2. 意图关键词匹配
        if intent:
            for keyword, domains in self._intent_map.items():
                if keyword in intent:
                    for domain in domains:
                        domain_val = domain.value
                        score = self.WEIGHT_INTENT
                        # 关键词完全匹配加分
                        if keyword == intent.strip():
                            score += 0.5
                        scores[domain_val] = scores.get(domain_val, 0) + score
                        result.intent_scores[domain_val] = result.intent_scores.get(
                            domain_val, 0
                        ) + score
                        if domain not in result.matched_domains:
                            result.matched_domains.append(domain)

        # 3. 情感标签匹配
        if emotion:
            emotion_lower = emotion.lower()
            domains = self._emotion_map.get(emotion_lower, [])
            for domain in domains:
                domain_val = domain.value
                scores[domain_val] = scores.get(domain_val, 0) + self.WEIGHT_EMOTION
                result.emotion_scores[domain_val] = result.emotion_scores.get(
                    domain_val, 0
                ) + self.WEIGHT_EMOTION
                if domain not in result.matched_domains:
                    result.matched_domains.append(domain)

        result.combined_scores = scores

        # 按分数排序 matched_domains
        def domain_sort_key(d: CapabilityDomain) -> float:
            return -scores.get(d.value, 0)

        result.matched_domains.sort(key=domain_sort_key)

        logger.info(
            "domain_match_completed",
            intent=intent[:50] if intent else "",
            emotion=emotion,
            matched_domains=[d.value for d in result.matched_domains],
            top_scores=dict(
                sorted(scores.items(), key=lambda x: -x[1])[:5]
            ),
        )

        return result

    def get_token_budget(self, domain: CapabilityDomain) -> int:
        """获取能力域的默认 token 预算"""
        return DOMAIN_TOKEN_BUDGETS.get(domain, 300)

    def register_intent_keyword(
        self, keyword: str, domains: list[CapabilityDomain]
    ) -> None:
        """动态注册意图关键词映射"""
        self._intent_map[keyword] = domains
        logger.debug(
            "intent_keyword_registered",
            keyword=keyword,
            domains=[d.value for d in domains],
        )

    def register_emotion_mapping(
        self, emotion: str, domains: list[CapabilityDomain]
    ) -> None:
        """动态注册情感映射"""
        self._emotion_map[emotion.lower()] = domains
        logger.debug(
            "emotion_mapping_registered",
            emotion=emotion,
            domains=[d.value for d in domains],
        )
