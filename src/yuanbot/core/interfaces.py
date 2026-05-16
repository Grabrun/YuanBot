"""YuanBot 核心接口定义（抽象基类）"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from yuanbot.core.types import (
    ChannelConfig,
    ChatChunk,
    ChatResponse,
    ContentType,
    Message,
    MessageContent,
    BotResponse,
    SendResult,
    ToolDefinition,
    ToolResult,
    UserMessage,
)


# ──────────────────────────────────────────────
# AI 提供商适配器接口
# ──────────────────────────────────────────────

class AIProviderAdapter(ABC):
    """AI 提供商适配器统一接口
    
    所有 LLM 提供商（OpenAI、Claude、DeepSeek、Ollama 等）
    都必须实现此接口，实现零供应商锁定。
    """

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
    ) -> ChatResponse:
        """发送对话请求并获取响应"""
        ...

    @abstractmethod
    async def stream_chat_completion(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """流式对话请求"""
        ...

    @abstractmethod
    async def get_embedding(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float]:
        """获取文本向量嵌入（用于记忆语义检索）"""
        ...

    @property
    @abstractmethod
    def supported_models(self) -> list[str]:
        """返回该提供商支持的模型列表"""
        ...

    @property
    @abstractmethod
    def max_context_length(self) -> int:
        """返回最大上下文长度（Token 数），用于 Token 预算管理"""
        ...

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """返回提供商唯一标识（如 'openai', 'anthropic', 'deepseek'）"""
        ...


# ──────────────────────────────────────────────
# 消息通道适配器接口
# ──────────────────────────────────────────────

class ChannelAdapter(ABC):
    """消息通道适配器统一接口
    
    每种消息平台（Telegram/微信/Discord 等）实现此接口，
    将平台差异统一标准化为 UserMessage / BotResponse。
    """

    @abstractmethod
    async def initialize(self, config: ChannelConfig) -> None:
        """初始化适配器（连接、认证）"""
        ...

    @abstractmethod
    async def listen(
        self,
        callback: Callable[[UserMessage], Awaitable[BotResponse]],
    ) -> None:
        """启动消息监听，将每个收到的用户消息通过回调交给编排层处理"""
        ...

    @abstractmethod
    async def send_message(
        self,
        target_id: str,
        content: MessageContent,
    ) -> SendResult:
        """向指定目标发送消息"""
        ...

    @abstractmethod
    def get_platform_user_id(self, raw_event: Any) -> str:
        """从原始事件中提取平台用户 ID（用于跨平台身份链接）"""
        ...

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """返回平台名称（如 'telegram', 'wechat', 'discord'）"""
        ...

    @property
    @abstractmethod
    def supported_content_types(self) -> list[ContentType]:
        """返回支持的消息内容类型"""
        ...


# ──────────────────────────────────────────────
# Skill 模块接口
# ──────────────────────────────────────────────

class SkillMetadata(ABC):
    """Skill 元数据（用于索引和匹配）"""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    @abstractmethod
    def category(self) -> str:
        """"emotional" | "creative" | "utility" """
        ...

    @property
    @abstractmethod
    def capability_tags(self) -> list[str]:
        """能力标签，用于语义匹配"""
        ...

    @property
    @abstractmethod
    def token_cost(self) -> int:
        """预估 Token 占用"""
        ...


class SkillModule(ABC):
    """Skill 模块接口
    
    Skills 是可复用的工作流程与知识模块（偏向"软能力"），
    封装了特定场景的完整处理逻辑与专业知识。
    """

    @abstractmethod
    def get_metadata(self) -> SkillMetadata:
        """返回 Skill 元数据（用于索引）"""
        ...

    @abstractmethod
    def get_definition(self) -> str:
        """返回 Skill 完整定义（提示词、步骤、参数）"""
        ...

    @abstractmethod
    async def execute(
        self,
        context: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行 Skill"""
        ...


# ──────────────────────────────────────────────
# Tool 模块接口
# ──────────────────────────────────────────────

class ToolModule(ABC):
    """Tool 模块接口
    
    Tools 是可调用的外部功能接口（偏向"硬能力"），
    是对外部 API、系统功能的标准化封装。
    """

    @abstractmethod
    def get_schema(self) -> ToolDefinition:
        """返回工具定义（JSON Schema 格式）"""
        ...

    @abstractmethod
    async def invoke(
        self,
        params: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        """调用工具"""
        ...

    @property
    def permission_level(self) -> str:
        """权限级别: "safe" | "restricted" | "dangerous" """
        return "safe"


# ──────────────────────────────────────────────
# Agent 人设接口
# ──────────────────────────────────────────────

class PersonaProfile(ABC):
    """Agent 人设配置接口
    
    决定 AI 角色的人格特质、行为模式、语言风格。
    是 Skills/Tools 动态加载决策的主体。
    """

    @property
    @abstractmethod
    def persona_id(self) -> str:
        """人设唯一标识"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """角色名称"""
        ...

    @abstractmethod
    def get_system_prompt(self) -> str:
        """返回系统提示词（包含人设、行为规则、语气风格）"""
        ...

    @abstractmethod
    def get_behavior_rules(self) -> list[str]:
        """返回行为规则列表"""
        ...

    @abstractmethod
    def get_voice_style(self) -> dict[str, Any]:
        """返回语言风格配置"""
        ...

    @abstractmethod
    def get_capability_domains(self) -> list[str]:
        """返回能力域声明（用于 Skills/Tools 动态加载匹配）
        例: ["emotional_care", "daily_chat", "creative_storytelling"]
        """
        ...

    @abstractmethod
    def should_use_skill(self, skill_metadata: SkillMetadata) -> bool:
        """根据人设判断是否应使用某个 Skill"""
        ...
