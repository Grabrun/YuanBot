"""Skill 链式组合框架

支持多个 Skill 组成流水线执行，例如：安抚 → 讲笑话 → 转移注意力。

设计参考: capability-tool-system.md 第13节 扩展性蓝图 - Skill 链式组合
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ChainTrigger(Enum):
    """链式组合触发条件"""

    ALWAYS = "always"  # 始终触发
    EMOTION_LOW = "emotion_low"  # 情绪低落时触发
    EMOTION_HIGH = "emotion_high"  # 情绪高涨时触发
    INTENT_MATCH = "intent_match"  # 意图匹配时触发
    USER_REQUEST = "user_request"  # 用户主动请求时触发
    SILENCE = "silence"  # 用户沉默时触发


class ChainStepStatus(Enum):
    """链步骤执行状态"""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class ChainStep:
    """链式组合中的单个步骤"""

    skill_id: str
    trigger: ChainTrigger = ChainTrigger.ALWAYS
    condition: str | None = None  # 可选的条件表达式（简单字符串匹配）
    token_budget: int | None = None  # 该步骤的 token 预算
    timeout_seconds: int = 30  # 步骤超时
    fallback_skill_id: str | None = None  # 失败时的降级 Skill
    status: ChainStepStatus = ChainStepStatus.PENDING
    result: str | None = None
    started_at: float | None = None
    completed_at: float | None = None


@dataclass
class SkillChain:
    """Skill 链式组合定义"""

    chain_id: str
    name: str
    description: str = ""
    steps: list[ChainStep] = field(default_factory=list)
    trigger: ChainTrigger = ChainTrigger.ALWAYS
    max_total_tokens: int = 2000  # 整条链的最大 token 预算
    max_duration_seconds: int = 120  # 整条链的最大执行时间
    persona_filters: list[str] = field(default_factory=list)  # 适用的人格 ID
    priority: int = 0  # 优先级，数值越大越优先
    enabled: bool = True

    @property
    def total_token_estimate(self) -> int:
        """估算整条链的 token 消耗"""
        return sum(s.token_budget or 200 for s in self.steps)


@dataclass
class ChainExecutionResult:
    """链式组合执行结果"""

    chain_id: str
    success: bool
    completed_steps: int
    total_steps: int
    final_output: str = ""
    step_outputs: list[str] = field(default_factory=list)
    total_tokens_used: int = 0
    duration_seconds: float = 0.0
    error: str | None = None


class SkillChainManager:
    """Skill 链式组合管理器

    管理链式组合的注册、匹配和执行。

    使用方式::

        manager = SkillChainManager()

        # 注册链式组合
        chain = SkillChain(
            chain_id="comfort_then_distract",
            name="安抚后转移注意力",
            steps=[
                ChainStep(skill_id="emotional_comfort"),
                ChainStep(skill_id="creative_storytelling"),
            ],
            trigger=ChainTrigger.EMOTION_LOW,
        )
        manager.register_chain(chain)

        # 匹配可用的链
        chains = manager.match_chains(emotion="sadness")

        # 执行链
        result = await manager.execute_chain(
            chain,
            context_builder=my_context_builder,
            llm_caller=my_llm_call,
        )
    """

    def __init__(self) -> None:
        self._chains: dict[str, SkillChain] = {}

    def register_chain(self, chain: SkillChain) -> None:
        """注册链式组合"""
        self._chains[chain.chain_id] = chain
        logger.info(
            "skill_chain_registered",
            chain_id=chain.chain_id,
            name=chain.name,
            steps=len(chain.steps),
            trigger=chain.trigger.value,
        )

    def unregister_chain(self, chain_id: str) -> bool:
        """注销链式组合"""
        if chain_id in self._chains:
            del self._chains[chain_id]
            logger.info("skill_chain_unregistered", chain_id=chain_id)
            return True
        return False

    def get_chain(self, chain_id: str) -> SkillChain | None:
        """获取链式组合定义"""
        return self._chains.get(chain_id)

    def list_chains(self) -> list[SkillChain]:
        """列出所有已注册的链式组合"""
        return list(self._chains.values())

    def match_chains(
        self,
        intent: str = "",
        emotion: str = "",
        capability_domains: list[str] | None = None,
        persona_id: str | None = None,
    ) -> list[SkillChain]:
        """匹配当前上下文可用的链式组合

        Args:
            intent: 用户意图
            emotion: 情感标签
            capability_domains: 人设能力域
            persona_id: 当前人格 ID

        Returns:
            按优先级排序的匹配链列表
        """
        matched: list[tuple[SkillChain, int]] = []

        for chain in self._chains.values():
            if not chain.enabled:
                continue

            # 人格过滤
            if chain.persona_filters and persona_id and persona_id not in chain.persona_filters:
                continue

            score = chain.priority
            triggered = False

            # 触发条件匹配
            if chain.trigger == ChainTrigger.ALWAYS:
                score += 1
                triggered = True
            elif chain.trigger == ChainTrigger.EMOTION_LOW:
                low_emotions = {"sadness", "anger", "fear", "anxiety", "loneliness"}
                if emotion.lower() in low_emotions:
                    score += 3
                    triggered = True
            elif chain.trigger == ChainTrigger.EMOTION_HIGH:
                high_emotions = {"joy", "excitement", "love", "surprise"}
                if emotion.lower() in high_emotions:
                    score += 3
                    triggered = True
            elif chain.trigger == ChainTrigger.INTENT_MATCH:
                if intent:
                    for step in chain.steps:
                        if step.condition and step.condition in intent:
                            score += 2
                            triggered = True
                            break
            elif chain.trigger == ChainTrigger.USER_REQUEST:
                chain_keywords = [chain.name, chain.chain_id, "链", "组合", "流程"]
                if any(kw in intent for kw in chain_keywords):
                    score += 5
                    triggered = True
            elif chain.trigger == ChainTrigger.SILENCE:
                score += 1
                triggered = True  # 静默触发由外部判断

            if triggered:
                matched.append((chain, score))

        # 按分数降序排列
        matched.sort(key=lambda x: -x[1])
        result = [chain for chain, _ in matched]

        logger.debug(
            "skill_chain_matched",
            intent=intent[:50] if intent else "",
            emotion=emotion,
            matched_count=len(result),
            chain_ids=[c.chain_id for c in result],
        )

        return result

    @staticmethod
    async def execute_chain(
        chain: SkillChain,
        skill_prompt_getter: callable,
        llm_caller: callable,
        context: dict[str, Any] | None = None,
    ) -> ChainExecutionResult:
        """执行链式组合

        按顺序执行链中的每个步骤，将前一步的输出作为后一步的上下文。

        Args:
            chain: 要执行的链式组合
            skill_prompt_getter: 获取 Skill 提示词的函数 (skill_id) -> str
            llm_caller: 调用 LLM 的函数 (system_prompt, user_input) -> str
            context: 额外上下文信息

        Returns:
            ChainExecutionResult: 执行结果
        """
        start_time = time.monotonic()
        result = ChainExecutionResult(
            chain_id=chain.chain_id,
            success=False,
            completed_steps=0,
            total_steps=len(chain.steps),
        )

        accumulated_output = ""
        total_tokens = 0

        for i, step in enumerate(chain.steps):
            # 检查超时
            elapsed = time.monotonic() - start_time
            if elapsed > chain.max_duration_seconds:
                logger.warning(
                    "chain_timeout",
                    chain_id=chain.chain_id,
                    elapsed=elapsed,
                    max=chain.max_duration_seconds,
                )
                step.status = ChainStepStatus.SKIPPED
                result.error = f"Chain timed out after {elapsed:.1f}s"
                break

            # 检查 token 预算
            if total_tokens >= chain.max_total_tokens:
                logger.warning(
                    "chain_token_budget_exceeded",
                    chain_id=chain.chain_id,
                    total_tokens=total_tokens,
                    max=chain.max_total_tokens,
                )
                step.status = ChainStepStatus.SKIPPED
                result.error = f"Token budget exceeded ({total_tokens}/{chain.max_total_tokens})"
                break

            # 获取 Skill 提示词
            prompt = skill_prompt_getter(step.skill_id)
            if not prompt:
                logger.warning(
                    "chain_step_prompt_not_found",
                    chain_id=chain.chain_id,
                    step=i,
                    skill_id=step.skill_id,
                )
                step.status = ChainStepStatus.FAILED
                # 尝试降级
                if step.fallback_skill_id:
                    prompt = skill_prompt_getter(step.fallback_skill_id)
                    if prompt:
                        logger.info(
                            "chain_step_fallback",
                            chain_id=chain.chain_id,
                            from_skill=step.skill_id,
                            to_skill=step.fallback_skill_id,
                        )
                if not prompt:
                    result.error = f"Skill '{step.skill_id}' not found and no fallback"
                    break

            # 执行步骤
            step.status = ChainStepStatus.ACTIVE
            step.started_at = time.monotonic()

            try:
                user_input = accumulated_output if i > 0 else (context or {}).get(
                    "user_message", ""
                )
                step_output = await llm_caller(prompt, user_input)
                step.result = step_output
                step.status = ChainStepStatus.COMPLETED
                step.completed_at = time.monotonic()

                accumulated_output = step_output
                result.step_outputs.append(step_output)
                result.completed_steps += 1

                # 估算 token（简单估算：1 token ≈ 2 中文字 或 4 英文字符）
                est_tokens = len(prompt) // 2 + len(step_output) // 2
                total_tokens += est_tokens
                result.total_tokens_used = total_tokens

                logger.debug(
                    "chain_step_completed",
                    chain_id=chain.chain_id,
                    step=i,
                    skill_id=step.skill_id,
                    output_len=len(step_output),
                )

            except Exception as exc:
                step.status = ChainStepStatus.FAILED
                step.completed_at = time.monotonic()
                logger.error(
                    "chain_step_failed",
                    chain_id=chain.chain_id,
                    step=i,
                    skill_id=step.skill_id,
                    error=str(exc),
                )
                result.error = f"Step {i} ({step.skill_id}) failed: {exc}"
                break

        result.final_output = accumulated_output
        result.duration_seconds = time.monotonic() - start_time
        result.success = result.completed_steps == result.total_steps

        logger.info(
            "chain_execution_completed",
            chain_id=chain.chain_id,
            success=result.success,
            completed=result.completed_steps,
            total=result.total_steps,
            duration=f"{result.duration_seconds:.2f}s",
            tokens=result.total_tokens_used,
        )

        return result

    def create_chain_from_config(self, config: dict[str, Any]) -> SkillChain:
        """从配置字典创建链式组合

        Args:
            config: 链式组合配置字典

        Returns:
            SkillChain 实例
        """
        steps = []
        for step_cfg in config.get("steps", []):
            step = ChainStep(
                skill_id=step_cfg["skill_id"],
                trigger=ChainTrigger(step_cfg.get("trigger", "always")),
                condition=step_cfg.get("condition"),
                token_budget=step_cfg.get("token_budget"),
                timeout_seconds=step_cfg.get("timeout_seconds", 30),
                fallback_skill_id=step_cfg.get("fallback_skill_id"),
            )
            steps.append(step)

        chain = SkillChain(
            chain_id=config["chain_id"],
            name=config.get("name", config["chain_id"]),
            description=config.get("description", ""),
            steps=steps,
            trigger=ChainTrigger(config.get("trigger", "always")),
            max_total_tokens=config.get("max_total_tokens", 2000),
            max_duration_seconds=config.get("max_duration_seconds", 120),
            persona_filters=config.get("persona_filters", []),
            priority=config.get("priority", 0),
            enabled=config.get("enabled", True),
        )

        return chain
