"""Token 预算管理器

在有限的上下文窗口内最大化推理质量。
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# 估算的 Token 比率（中文约 1.5 字/token，英文约 4 字符/token）
_AVG_CHARS_PER_TOKEN = 3.0


class TokenBudgetManager:
    """Token 预算管理器

    职责：
    1. 估算各部分的 Token 消耗
    2. 在预算内分配空间
    3. 在超限时裁剪低优先级内容
    """

    def __init__(self, max_tokens: int = 128000, response_reserve: int = 4096):
        self._max_tokens = max_tokens
        self._response_reserve = response_reserve

    @property
    def available_tokens(self) -> int:
        """可用于上下文的 Token 数"""
        return self._max_tokens - self._response_reserve

    def estimate_tokens(self, text: str) -> int:
        """估算文本的 Token 数"""
        if not text:
            return 0
        return max(1, int(len(text) / _AVG_CHARS_PER_TOKEN))

    def allocate_budget(
        self,
        sections: dict[str, str],
        priorities: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """在预算内分配各段落

        Args:
            sections: {name: content} 字典
            priorities: {name: priority} 字典，priority 为 "high" | "normal" | "low"

        Returns:
            裁剪后的 {name: content} 字典
        """
        priorities = priorities or {}
        budget = self.available_tokens

        # 按优先级排序
        high = []
        normal = []
        low = []

        for name, content in sections.items():
            priority = priorities.get(name, "normal")
            if priority == "high":
                high.append((name, content))
            elif priority == "low":
                low.append((name, content))
            else:
                normal.append((name, content))

        result: dict[str, str] = {}
        used_tokens = 0

        # 高优先级：完整保留
        for name, content in high:
            tokens = self.estimate_tokens(content)
            if used_tokens + tokens <= budget:
                result[name] = content
                used_tokens += tokens

        # 普通优先级：尽可能保留
        for name, content in normal:
            tokens = self.estimate_tokens(content)
            if used_tokens + tokens <= budget:
                result[name] = content
                used_tokens += tokens
            else:
                # 尝试裁剪
                remaining = budget - used_tokens
                if remaining > 50:  # 至少保留 50 tokens
                    result[name] = self._truncate_to_tokens(content, remaining)
                    used_tokens += remaining
                break

        # 低优先级：仅在有剩余空间时保留
        for name, content in low:
            tokens = self.estimate_tokens(content)
            if used_tokens + tokens <= budget:
                result[name] = content
                used_tokens += tokens

        logger.debug(
            "budget_allocated",
            total_tokens=used_tokens,
            budget=budget,
            sections=len(result),
        )

        return result

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """将文本裁剪到指定 Token 数"""
        max_chars = int(max_tokens * _AVG_CHARS_PER_TOKEN)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."

    def get_budget_status(self) -> dict[str, int]:
        """获取预算状态"""
        return {
            "max_tokens": self._max_tokens,
            "response_reserve": self._response_reserve,
            "available_tokens": self.available_tokens,
        }
