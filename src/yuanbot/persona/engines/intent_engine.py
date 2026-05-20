"""意图识别引擎

识别用户输入的核心意图，为后续决策和能力选择提供基础分类。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class IntentResult:
    """意图识别结果"""

    primary: str  # 主要意图
    secondary: list[str] = field(default_factory=list)  # 次要意图
    confidence: float = 0.5  # 置信度 0.0 ~ 1.0
    entities: dict[str, Any] = field(default_factory=dict)  # 提取的实体


# 意图模式定义
_INTENT_PATTERNS: dict[str, dict[str, Any]] = {
    "greeting": {
        "keywords": ["你好", "hi", "hello", "嗨", "早上好", "晚上好", "早安", "晚安"],
        "priority": 1,
    },
    "farewell": {
        "keywords": ["再见", "拜拜", "bye", "byebye", "晚安", "下次见"],
        "priority": 1,
    },
    "emotional_seeking_comfort": {
        "keywords": [
            "难过",
            "伤心",
            "不开心",
            "烦",
            "压力大",
            "焦虑",
            "害怕",
            "孤独",
            "失落",
            "委屈",
            "想哭",
            "崩溃",
        ],
        "priority": 3,
    },
    "emotional_sharing_joy": {
        "keywords": [
            "开心",
            "高兴",
            "太好了",
            "哈哈",
            "恭喜",
            "棒",
            "厉害",
            "成功",
            "通过了",
            "拿到了",
        ],
        "priority": 2,
    },
    "seeking_advice": {
        "keywords": ["怎么办", "你觉得", "建议", "意见", "帮我", "应该怎么", "有什么办法"],
        "priority": 2,
    },
    "casual_chat": {
        "keywords": ["无聊", "聊聊", "在干嘛", "你在吗", "说说", "讲讲"],
        "priority": 1,
    },
    "asking_question": {
        "keywords": ["什么", "为什么", "怎么", "哪里", "谁", "几", "吗", "？"],
        "priority": 1,
    },
    "request_action": {
        "keywords": ["帮我", "提醒我", "设置", "创建", "搜索", "查一下", "打开"],
        "priority": 2,
    },
    "expressing_gratitude": {
        "keywords": ["谢谢", "感谢", "多谢", "thank", "thx"],
        "priority": 1,
    },
}

# 命令模式（高置信度直接匹配）
_COMMAND_PATTERNS: dict[str, str] = {
    r"^/set_reminder": "set_reminder",
    r"^/search": "search",
    r"^/translate": "translate",
    r"^/help": "help",
    r"^/status": "status",
    r"^/memory": "memory_query",
}


class IntentEngine:
    """意图识别引擎

    实现方式：
    1. 规则优先：命令式意图直接匹配
    2. 关键词匹配：基于意图词典
    3. 可扩展：后续接入模型分类器
    """

    def __init__(self, custom_patterns: dict[str, dict[str, Any]] | None = None):
        self._patterns = {**_INTENT_PATTERNS, **(custom_patterns or {})}

    def recognize(self, text: str) -> IntentResult:
        """识别用户意图

        Args:
            text: 用户输入文本

        Returns:
            IntentResult: 意图识别结果
        """
        if not text or not text.strip():
            return IntentResult(primary="empty", confidence=1.0)

        text_clean = text.strip()
        text_lower = text_clean.lower()

        # 1. 命令模式匹配（高置信度）
        for pattern, intent in _COMMAND_PATTERNS.items():
            if re.match(pattern, text_clean):
                return IntentResult(
                    primary=intent,
                    confidence=0.99,
                    entities={"command": text_clean.split()[0]},
                )

        # 2. 关键词匹配
        scores: dict[str, float] = {}
        matched_keywords: dict[str, list[str]] = {}

        for intent, config in self._patterns.items():
            keywords = config.get("keywords", [])
            priority = config.get("priority", 1)
            matched = [kw for kw in keywords if kw in text_lower]

            if matched:
                # 分数 = 匹配数量 * 优先级权重
                score = len(matched) * (priority * 0.3)
                scores[intent] = min(score, 1.0)
                matched_keywords[intent] = matched

        if not scores:
            return IntentResult(primary="unknown", confidence=0.3)

        # 按分数排序
        sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        primary = sorted_intents[0][0]
        confidence = min(sorted_intents[0][1], 1.0)
        secondary = [intent for intent, _ in sorted_intents[1:3]]  # 最多2个次要意图

        # 提取实体
        entities: dict[str, Any] = {}
        if primary in matched_keywords:
            entities["matched_keywords"] = matched_keywords[primary]

        result = IntentResult(
            primary=primary,
            secondary=secondary,
            confidence=confidence,
            entities=entities,
        )

        logger.debug(
            "intent_recognized",
            primary=primary,
            confidence=confidence,
            secondary=secondary,
        )

        return result
