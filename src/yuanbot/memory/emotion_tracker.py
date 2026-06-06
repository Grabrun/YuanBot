"""YuanBot 情感追踪系统

实现情感分析、记录、趋势分析和模式识别功能。
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import structlog

from yuanbot.core.types import (
    EmotionCategory,
    EmotionPattern,
    EmotionRecord,
    EmotionState,
    EmotionTrend,
)

logger = structlog.get_logger(__name__)

# 情感词典（简化版，实际应用中可加载更完整的词典）
EMOTION_LEXICON: dict[str, dict[str, float]] = {
    # 喜悦相关
    "开心": {"joy": 0.9, "valence": 0.9},
    "高兴": {"joy": 0.85, "valence": 0.85},
    "快乐": {"joy": 0.9, "valence": 0.9},
    "幸福": {"joy": 0.95, "valence": 0.95},
    "喜欢": {"joy": 0.7, "trust": 0.6, "valence": 0.8},
    "爱": {"joy": 0.9, "trust": 0.8, "valence": 0.9},
    "太好了": {"joy": 0.8, "surprise": 0.3, "valence": 0.8},
    "哈哈": {"joy": 0.7, "valence": 0.7},
    "嘻嘻": {"joy": 0.6, "valence": 0.6},
    # 悲伤相关
    "难过": {"sadness": 0.8, "valence": -0.7},
    "伤心": {"sadness": 0.85, "valence": -0.8},
    "哭": {"sadness": 0.7, "valence": -0.6},
    "想念": {"sadness": 0.5, "anticipation": 0.4, "valence": -0.3},
    "孤独": {"sadness": 0.7, "fear": 0.3, "valence": -0.6},
    "失落": {"sadness": 0.75, "valence": -0.7},
    "遗憾": {"sadness": 0.6, "valence": -0.5},
    # 愤怒相关
    "生气": {"anger": 0.8, "valence": -0.7},
    "愤怒": {"anger": 0.9, "valence": -0.8},
    "烦": {"anger": 0.5, "disgust": 0.3, "valence": -0.4},
    "讨厌": {"anger": 0.6, "disgust": 0.5, "valence": -0.6},
    "恨": {"anger": 0.85, "disgust": 0.4, "valence": -0.8},
    # 恐惧相关
    "害怕": {"fear": 0.8, "valence": -0.6},
    "担心": {"fear": 0.6, "anticipation": 0.3, "valence": -0.4},
    "焦虑": {"fear": 0.7, "anger": 0.2, "valence": -0.6},
    "紧张": {"fear": 0.5, "anticipation": 0.4, "valence": -0.3},
    "恐惧": {"fear": 0.9, "valence": -0.8},
    # 惊讶相关
    "惊讶": {"surprise": 0.8, "valence": 0.1},
    "意外": {"surprise": 0.7, "valence": 0.0},
    "天啊": {"surprise": 0.8, "valence": 0.2},
    "哇": {"surprise": 0.6, "joy": 0.3, "valence": 0.4},
    # 厌恶相关
    "恶心": {"disgust": 0.8, "valence": -0.7},
    "受不了": {"disgust": 0.6, "anger": 0.4, "valence": -0.6},
    "无聊": {"disgust": 0.4, "sadness": 0.3, "valence": -0.3},
    # 信任相关
    "信任": {"trust": 0.8, "valence": 0.6},
    "相信": {"trust": 0.7, "valence": 0.5},
    "依赖": {"trust": 0.6, "fear": 0.2, "valence": 0.3},
    # 期待相关
    "期待": {"anticipation": 0.8, "joy": 0.4, "valence": 0.6},
    "希望": {"anticipation": 0.7, "joy": 0.3, "valence": 0.5},
    "梦想": {"anticipation": 0.8, "joy": 0.5, "valence": 0.7},
}

# 情感强度修饰词
INTENSITY_MODIFIERS: dict[str, float] = {
    "非常": 1.5,
    "特别": 1.4,
    "很": 1.3,
    "超级": 1.6,
    "太": 1.5,
    "有点": 0.7,
    "稍微": 0.6,
    "一点": 0.5,
    "略微": 0.6,
}

# 否定词（仅匹配独立的否定词）
NEGATION_WORDS = frozenset({"不", "没", "没有", "别", "莫", "勿", "未", "无"})
NEGATION_PATTERNS = ("不是", "不会", "不能", "不要", "没有", "别这样")

# 预排序情感词典键（按长度降序，优先匹配长词）——避免每次分析时重新排序
_SORTED_EMOTION_WORDS: tuple[str, ...] = tuple(
    sorted(EMOTION_LEXICON.keys(), key=len, reverse=True)
)

# 情感分类 frozenset 常量——避免每次方法调用时重新创建集合
_POSITIVE_EMOTIONS: frozenset[EmotionCategory] = frozenset({
    EmotionCategory.JOY, EmotionCategory.TRUST, EmotionCategory.ANTICIPATION,
})
_NEGATIVE_EMOTIONS: frozenset[EmotionCategory] = frozenset({
    EmotionCategory.SADNESS, EmotionCategory.ANGER,
    EmotionCategory.FEAR, EmotionCategory.DISGUST,
})
_HIGH_AROUSAL_EMOTIONS: frozenset[EmotionCategory] = frozenset({
    EmotionCategory.ANGER, EmotionCategory.FEAR, EmotionCategory.SURPRISE,
})
_LOW_AROUSAL_EMOTIONS: frozenset[EmotionCategory] = frozenset({
    EmotionCategory.SADNESS, EmotionCategory.TRUST,
})
_HIGH_DOMINANCE_EMOTIONS: frozenset[EmotionCategory] = frozenset({
    EmotionCategory.ANGER, EmotionCategory.DISGUST, EmotionCategory.JOY,
})
_LOW_DOMINANCE_EMOTIONS: frozenset[EmotionCategory] = frozenset({
    EmotionCategory.FEAR, EmotionCategory.SADNESS,
})
_COMFORT_EMOTIONS: frozenset[EmotionCategory] = frozenset({
    EmotionCategory.SADNESS, EmotionCategory.FEAR, EmotionCategory.ANGER,
})

# 否定词反转时使用的字符串常量（避免在循环中重复创建列表）
_NEGATION_POSITIVE_EMOTIONS: frozenset[str] = frozenset({"joy", "trust", "anticipation"})
_NEGATION_NEGATIVE_EMOTIONS: frozenset[str] = frozenset({"sadness", "anger", "fear", "disgust"})

# 预编译正则表达式（避免每次 _extract_keywords 调用时重新编译）
_NON_WORD_PATTERN: re.Pattern[str] = re.compile(r"[^\w\s]")


class EmotionTracker:
    """情感追踪系统

    职责：
    1. 分析用户消息中的情感色彩
    2. 记录情感变化历史
    3. 分析情感趋势
    4. 识别情感模式
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._records: dict[str, list[EmotionRecord]] = defaultdict(list)  # user_id -> records
        self._patterns: dict[str, list[EmotionPattern]] = defaultdict(list)  # user_id -> patterns
        self._session_emotions: dict[str, list[EmotionState]] = defaultdict(
            list
        )  # session_id -> emotions

    async def analyze_emotion(
        self,
        text: str,
        user_id: str,
        session_id: str,
        context_summary: str | None = None,
    ) -> EmotionState:
        """分析文本中的情感

        Args:
            text: 用户输入文本
            user_id: 用户 ID
            session_id: 会话 ID
            context_summary: 上下文摘要

        Returns:
            EmotionState: 情感状态分析结果
        """
        # 1. 基于规则的情感分析
        rule_result = self._analyze_with_rules(text)

        # 2. 考虑上下文调整
        if context_summary:
            context_emotion = self._analyze_with_rules(context_summary)
            # 上下文情感对当前情感有轻微影响
            for emotion, score in context_emotion.items():
                if emotion in rule_result:
                    rule_result[emotion] = rule_result[emotion] * 0.8 + score * 0.2

        # 3. 确定主要情感
        if not rule_result or all(v < 0.1 for v in rule_result.values()):
            primary_emotion = EmotionCategory.NEUTRAL
            intensity = 0.3
            valence = "neutral"
        else:
            primary_emotion_name = max(rule_result, key=rule_result.get)
            primary_emotion = EmotionCategory(primary_emotion_name)
            intensity = min(rule_result[primary_emotion_name], 1.0)
            valence = self._determine_valence(primary_emotion)

        # 4. 构建情感状态
        emotion_state = EmotionState(
            emotion=primary_emotion,
            intensity=intensity,
            valence=valence,
            arousal=self._determine_arousal(primary_emotion, intensity),
            dominance=self._determine_dominance(primary_emotion),
            needs_immediate_comfort=self._needs_comfort(primary_emotion, intensity),
            confidence=0.7 if rule_result else 0.3,
        )

        # 5. 记录情感
        record = EmotionRecord(
            user_id=user_id,
            session_id=session_id,
            emotion_state=emotion_state,
            trigger_text=text[:200],  # 限制长度
            context_summary=context_summary,
            analysis_method="rule_based",
            raw_scores=rule_result,
        )
        self._records[user_id].append(record)
        self._session_emotions[session_id].append(emotion_state)

        # 6. 检查是否需要更新情感模式
        await self._check_pattern_update(user_id, emotion_state, text)

        logger.debug(
            "emotion_analyzed",
            user_id=user_id,
            emotion=primary_emotion.value,
            intensity=intensity,
            valence=valence,
        )

        return emotion_state

    def _analyze_with_rules(self, text: str) -> dict[str, float]:
        """基于规则的情感分析"""
        scores: dict[str, float] = defaultdict(float)
        text_lower = text.lower()

        # 检查否定词
        has_negation = any(neg in text_lower for neg in NEGATION_WORDS)

        # 遍历情感词典（使用预排序的元组，按词长度降序，优先匹配长词）
        # 使用 find() 替代 in + find 双重搜索，减少一次字符串扫描
        for word in _SORTED_EMOTION_WORDS:
            word_pos = text_lower.find(word)
            if word_pos >= 0:
                # 检查前面是否有强度修饰词
                prefix = text_lower[max(0, word_pos - 6) : word_pos]

                intensity_multiplier = 1.0
                for modifier, mult in INTENSITY_MODIFIERS.items():
                    if modifier in prefix:
                        intensity_multiplier = mult
                        break

                # 添加情感分数
                for emotion, score in EMOTION_LEXICON[word].items():
                    if emotion != "valence":
                        adjusted_score = score * intensity_multiplier
                        if has_negation:
                            # 否定词反转情感（简化处理）
                            if emotion in _NEGATION_POSITIVE_EMOTIONS:
                                adjusted_score *= -0.5
                            elif emotion in _NEGATION_NEGATIVE_EMOTIONS:
                                adjusted_score *= 0.7
                        scores[emotion] += adjusted_score

        # 归一化
        if scores:
            max_score = max(scores.values())
            if max_score > 0:
                scores = {k: min(v / max_score, 1.0) for k, v in scores.items()}

        return dict(scores)

    @staticmethod
    def _determine_valence(emotion: EmotionCategory) -> str:
        """确定情感效价"""
        if emotion in _POSITIVE_EMOTIONS:
            return "positive"
        elif emotion in _NEGATIVE_EMOTIONS:
            return "negative"
        return "neutral"

    @staticmethod
    def _determine_arousal(emotion: EmotionCategory, intensity: float) -> str:
        """确定情感唤醒度"""
        if emotion in _HIGH_AROUSAL_EMOTIONS:
            return "high" if intensity > 0.5 else "medium"
        elif emotion in _LOW_AROUSAL_EMOTIONS:
            return "low" if intensity > 0.5 else "medium"
        return "medium"

    @staticmethod
    def _determine_dominance(emotion: EmotionCategory) -> str:
        """确定情感主导度"""
        if emotion in _HIGH_DOMINANCE_EMOTIONS:
            return "high"
        elif emotion in _LOW_DOMINANCE_EMOTIONS:
            return "low"
        return "medium"

    @staticmethod
    def _needs_comfort(emotion: EmotionCategory, intensity: float) -> bool:
        """判断是否需要立即安慰"""
        return emotion in _COMFORT_EMOTIONS and intensity > 0.6

    async def _check_pattern_update(
        self,
        user_id: str,
        emotion_state: EmotionState,
        text: str,
    ) -> None:
        """检查并更新情感模式"""
        # 简化实现：检查是否有重复的情感模式
        existing_patterns = self._patterns[user_id]

        # 查找相似的模式
        similar_pattern = None
        for pattern in existing_patterns:
            if (
                pattern.typical_response.emotion == emotion_state.emotion
                and pattern.pattern_type == "topic_based"
            ):
                # 检查话题相似性
                if any(
                    keyword in text for keyword in pattern.trigger_conditions.get("keywords", [])
                ):
                    similar_pattern = pattern
                    break

        if similar_pattern:
            # 更新现有模式
            similar_pattern.occurrence_count += 1
            similar_pattern.last_occurrence = datetime.now()
            similar_pattern.confidence = min(similar_pattern.confidence + 0.05, 0.95)
        else:
            # 创建新模式（如果出现3次以上相似情感）
            recent_records = self._records[user_id][-10:]  # 最近10条记录
            same_emotion_count = sum(
                1 for r in recent_records if r.emotion_state.emotion == emotion_state.emotion
            )

            if same_emotion_count >= 3:
                # 提取关键词
                keywords = self._extract_keywords(text)
                if keywords:
                    keywords_str = ", ".join(keywords[:3])
                    emotion_val = emotion_state.emotion.value
                    desc = f"用户在讨论{keywords_str}时倾向于{emotion_val}"
                    new_pattern = EmotionPattern(
                        user_id=user_id,
                        pattern_type="topic_based",
                        description=desc,
                        trigger_conditions={"keywords": keywords},
                        typical_response=emotion_state,
                        occurrence_count=same_emotion_count,
                        last_occurrence=datetime.now(),
                        confidence=0.5,
                    )
                    self._patterns[user_id].append(new_pattern)
                    logger.info(
                        "emotion_pattern_created",
                        user_id=user_id,
                        pattern_id=new_pattern.pattern_id,
                    )

    def _extract_keywords(self, text: str) -> list[str]:
        """提取文本中的关键词（简化实现）"""
        # 移除标点符号（使用预编译正则）
        text_clean = _NON_WORD_PATTERN.sub("", text)
        # 分词（简化：按空格分割，中文按字符）
        words = [word for word in text_clean.split() if len(word) > 1]
        # 对于中文，提取2-4字的词
        text_len = len(text_clean)
        for i in range(text_len - 1):
            end = min(i + 4, text_len)
            words.extend(
                text_clean[i : i + length] for length in range(2, end - i + 1)
            )
        return list(set(words))[:5]  # 返回最多5个关键词

    async def get_session_emotion_summary(self, session_id: str) -> dict[str, Any]:
        """获取会话的情感摘要"""
        emotions = self._session_emotions.get(session_id, [])
        if not emotions:
            return {"dominant_emotion": "neutral", "average_intensity": 0.3, "emotion_count": 0}

        # 统计情感分布
        emotion_counts: dict[str, int] = defaultdict(int)
        total_intensity = 0.0

        for emotion_state in emotions:
            emotion_counts[emotion_state.emotion.value] += 1
            total_intensity += emotion_state.intensity

        dominant_emotion = max(emotion_counts, key=emotion_counts.get)

        return {
            "dominant_emotion": dominant_emotion,
            "average_intensity": total_intensity / len(emotions),
            "emotion_count": len(emotions),
            "emotion_distribution": dict(emotion_counts),
            "needs_comfort": any(e.needs_immediate_comfort for e in emotions[-3:]),  # 最近3条
        }

    async def get_emotion_trend(
        self,
        user_id: str,
        period: str = "daily",
        days: int = 7,
    ) -> EmotionTrend:
        """获取情感趋势"""
        now = datetime.now()
        start_date = now - timedelta(days=days)

        # 筛选时间范围内的记录
        records = [r for r in self._records.get(user_id, []) if r.timestamp >= start_date]

        if not records:
            return EmotionTrend(
                user_id=user_id,
                period=period,
                start_date=start_date,
                end_date=now,
                dominant_emotion=EmotionCategory.NEUTRAL,
                emotion_distribution={},
                average_intensity=0.3,
                valence_ratio={"positive": 0.33, "negative": 0.33, "neutral": 0.34},
                mood_stability=0.5,
                emotional_variety=0.5,
                comfort_need_frequency=0.0,
            )

        # 统计情感分布
        emotion_counts: dict[EmotionCategory, int] = defaultdict(int)
        total_intensity = 0.0
        valence_counts: dict[str, int] = defaultdict(int)
        comfort_count = 0

        for record in records:
            emotion_counts[record.emotion_state.emotion] += 1
            total_intensity += record.emotion_state.intensity
            valence_counts[record.emotion_state.valence] += 1
            if record.emotion_state.needs_immediate_comfort:
                comfort_count += 1

        # 计算分布
        total_records = len(records)
        emotion_distribution = {
            emotion: count / total_records for emotion, count in emotion_counts.items()
        }

        valence_ratio = {
            valence: count / total_records for valence, count in valence_counts.items()
        }

        # 确定主导情感
        dominant_emotion = max(emotion_counts, key=emotion_counts.get)

        # 计算情绪稳定性（简化：基于情感变化频率）
        emotion_changes = 0
        for i in range(1, len(records)):
            if records[i].emotion_state.emotion != records[i - 1].emotion_state.emotion:
                emotion_changes += 1
        mood_stability = 1.0 - (emotion_changes / max(total_records - 1, 1))

        # 计算情感多样性
        unique_emotions = len(emotion_counts)
        emotional_variety = unique_emotions / len(EmotionCategory)

        return EmotionTrend(
            user_id=user_id,
            period=period,
            start_date=start_date,
            end_date=now,
            dominant_emotion=dominant_emotion,
            emotion_distribution=emotion_distribution,
            average_intensity=total_intensity / total_records,
            valence_ratio=valence_ratio,
            mood_stability=mood_stability,
            emotional_variety=emotional_variety,
            comfort_need_frequency=comfort_count / total_records,
        )

    async def get_user_patterns(self, user_id: str) -> list[EmotionPattern]:
        """获取用户的情感模式"""
        return self._patterns.get(user_id, [])

    async def get_comfort_suggestions(
        self,
        user_id: str,
        current_emotion: EmotionState,
    ) -> list[str]:
        """获取安慰建议"""
        suggestions = []

        if current_emotion.emotion == EmotionCategory.SADNESS:
            suggestions.extend(
                [
                    "我在这里陪着你，愿意和我说说发生了什么吗？",
                    "难过的时候不用忍着，我会一直在这里。",
                    "想哭就哭出来吧，我会陪着你的。",
                ]
            )
        elif current_emotion.emotion == EmotionCategory.FEAR:
            suggestions.extend(
                [
                    "别怕，有我在呢。",
                    "深呼吸，一切都会好起来的。",
                    "告诉我你在担心什么，我们一起想办法。",
                ]
            )
        elif current_emotion.emotion == EmotionCategory.ANGER:
            suggestions.extend(
                [
                    "我理解你现在很生气，先冷静一下好吗？",
                    "生气是正常的，但别让情绪伤害了自己。",
                    "愿意和我说说是什么让你这么生气吗？",
                ]
            )
        elif current_emotion.emotion == EmotionCategory.ANTICIPATION:
            suggestions.extend(
                [
                    "我也很期待呢！",
                    "希望一切都能如你所愿。",
                    "有什么我能帮忙的吗？",
                ]
            )
        else:
            suggestions.extend(
                [
                    "今天过得怎么样？",
                    "有什么想和我分享的吗？",
                    "我一直都在哦。",
                ]
            )

        return suggestions[:3]  # 返回最多3个建议
