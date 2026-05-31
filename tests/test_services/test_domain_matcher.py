"""能力域匹配器测试"""

from __future__ import annotations

import pytest

from yuanbot.services.domain_matcher import (
    CapabilityDomain,
    DomainMatcher,
    DomainMatchResult,
)


class TestDomainMatcherMatch:
    """测试核心匹配逻辑"""

    def test_empty_input(self):
        matcher = DomainMatcher()
        result = matcher.match()
        assert result.matched_domains == []
        assert result.combined_scores == {}

    def test_match_by_capability_domain(self):
        matcher = DomainMatcher()
        result = matcher.match(capability_domains=["emotional_care"])
        assert CapabilityDomain.EMOTIONAL_CARE in result.matched_domains
        assert result.combined_scores["emotional_care"] == 3.0  # WEIGHT_DOMAIN_DECLARATION

    def test_match_by_intent_keyword(self):
        matcher = DomainMatcher()
        result = matcher.match(intent="我好难过")
        assert CapabilityDomain.EMOTIONAL_CARE in result.matched_domains
        assert result.combined_scores["emotional_care"] == 2.0  # WEIGHT_INTENT

    def test_match_by_emotion(self):
        matcher = DomainMatcher()
        result = matcher.match(emotion="sadness")
        assert CapabilityDomain.EMOTIONAL_CARE in result.matched_domains
        assert result.combined_scores["emotional_care"] == 1.0  # WEIGHT_EMOTION

    def test_combined_scoring(self):
        matcher = DomainMatcher()
        result = matcher.match(
            intent="我好难过",
            emotion="sadness",
            capability_domains=["emotional_care"],
        )
        # domain declaration (3.0) + intent (2.0) + emotion (1.0) = 6.0
        assert result.combined_scores["emotional_care"] == 6.0

    def test_multiple_domains(self):
        matcher = DomainMatcher()
        result = matcher.match(
            intent="我想听故事",
            capability_domains=["emotional_care"],
        )
        # emotional_care from declaration, creative_storytelling from intent
        assert CapabilityDomain.EMOTIONAL_CARE in result.matched_domains
        assert CapabilityDomain.CREATIVE_STORYTELLING in result.matched_domains

    def test_exact_intent_match_bonus(self):
        matcher = DomainMatcher()
        result_exact = matcher.match(intent="故事")
        result_partial = matcher.match(intent="我想听一个故事")
        # Exact match should get higher score
        exact_score = result_exact.combined_scores.get("creative_storytelling", 0)
        partial_score = result_partial.combined_scores.get("creative_storytelling", 0)
        assert exact_score > partial_score

    def test_domains_sorted_by_score(self):
        matcher = DomainMatcher()
        result = matcher.match(
            intent="我好难过想听故事",
            emotion="sadness",
            capability_domains=["emotional_care"],
        )
        # emotional_care should be first (highest score)
        assert result.matched_domains[0] == CapabilityDomain.EMOTIONAL_CARE

    def test_unknown_capability_domain(self):
        matcher = DomainMatcher()
        result = matcher.match(capability_domains=["custom_domain"])
        assert "custom_domain" in result.combined_scores
        assert result.combined_scores["custom_domain"] == 3.0

    def test_recommendation_counts(self):
        matcher = DomainMatcher()
        result = matcher.match(max_skills=5, max_tools=10)
        assert result.recommended_skill_count == 5
        assert result.recommended_tool_count == 10

    def test_intent_scores_tracked(self):
        matcher = DomainMatcher()
        result = matcher.match(intent="我好难过")
        assert "emotional_care" in result.intent_scores

    def test_emotion_scores_tracked(self):
        matcher = DomainMatcher()
        result = matcher.match(emotion="sadness")
        assert "emotional_care" in result.emotion_scores


class TestDomainMatcherRegistration:
    """测试动态注册"""

    def test_register_intent_keyword(self):
        matcher = DomainMatcher()
        matcher.register_intent_keyword("自定义关键词", [CapabilityDomain.KNOWLEDGE_QUERY])
        result = matcher.match(intent="自定义关键词")
        assert CapabilityDomain.KNOWLEDGE_QUERY in result.matched_domains

    def test_register_emotion_mapping(self):
        matcher = DomainMatcher()
        matcher.register_emotion_mapping("custom_emotion", [CapabilityDomain.DAILY_CHAT])
        result = matcher.match(emotion="custom_emotion")
        assert CapabilityDomain.DAILY_CHAT in result.matched_domains


class TestDomainMatcherTokenBudget:
    """测试 token 预算"""

    def test_known_domain_budget(self):
        matcher = DomainMatcher()
        budget = matcher.get_token_budget(CapabilityDomain.CREATIVE_STORYTELLING)
        assert budget == 800

    def test_unknown_domain_default_budget(self):
        matcher = DomainMatcher()
        # CapabilityDomain.EMOTIONAL_CARE has a defined budget
        budget = matcher.get_token_budget(CapabilityDomain.EMOTIONAL_CARE)
        assert budget == 500


class TestDomainMatcherCustomMaps:
    """测试自定义映射表"""

    def test_custom_intent_map(self):
        custom_map = {"test_keyword": [CapabilityDomain.TASK_MANAGEMENT]}
        matcher = DomainMatcher(intent_domain_map=custom_map)
        result = matcher.match(intent="test_keyword")
        assert CapabilityDomain.TASK_MANAGEMENT in result.matched_domains

    def test_custom_emotion_map(self):
        custom_map = {"test_emotion": [CapabilityDomain.MEDIA_GENERATION]}
        matcher = DomainMatcher(emotion_domain_map=custom_map)
        result = matcher.match(emotion="test_emotion")
        assert CapabilityDomain.MEDIA_GENERATION in result.matched_domains
