"""YuanBot Extension Standard (Y.E.S.)

定义五种扩展类型的标准化接口和 manifest.json 规范。
社区开发者可按此标准开发、分享和发布扩展。

扩展类型：
1. AI Provider Adapter
2. Channel Adapter
3. Skill
4. Tool
5. Persona

设计参考: development-standards-ecosystem.md
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ── Manifest Schema 定义 ──────────────────────

MANIFEST_SCHEMA_VERSION = "1.0"


def parse_version(version: str) -> tuple[int, ...]:
    """解析语义化版本号

    Args:
        version: 版本号字符串，如 "1.2.3"

    Returns:
        版本号元组，如 (1, 2, 3)
    """
    parts = version.strip().split(".")
    result = []
    for part in parts:
        try:
            result.append(int(part))
        except ValueError:
            result.append(0)
    return tuple(result)


def compare_versions(v1: str, v2: str) -> int:
    """比较两个版本号

    Args:
        v1: 版本号 1
        v2: 版本号 2

    Returns:
        -1 if v1 < v2, 0 if equal, 1 if v1 > v2
    """
    parsed1 = parse_version(v1)
    parsed2 = parse_version(v2)
    # 补齐长度
    max_len = max(len(parsed1), len(parsed2))
    padded1 = parsed1 + (0,) * (max_len - len(parsed1))
    padded2 = parsed2 + (0,) * (max_len - len(parsed2))
    if padded1 < padded2:
        return -1
    elif padded1 > padded2:
        return 1
    return 0


def is_version_compatible(required: str, available: str) -> bool:
    """检查版本兼容性

    规则：主版本号必须相同，可用版本 >= 所需版本。

    Args:
        required: 所需版本
        available: 可用版本

    Returns:
        是否兼容
    """
    if not required.strip() or not available.strip():
        return True
    req = parse_version(required)
    avail = parse_version(available)
    if len(req) == 0 or len(avail) == 0:
        return True
    # 主版本号必须相同
    if req[0] != avail[0]:
        return False
    return compare_versions(available, required) >= 0

EXTENSION_TYPES = {
    "ai_provider": "AI 提供商适配器",
    "channel": "消息通道适配器",
    "skill": "技能模块",
    "tool": "工具模块",
    "persona": "人设包",
}


@dataclass
class ExtensionManifest:
    """扩展清单文件 (manifest.json)

    每个扩展包必须包含此文件，定义扩展的元数据、依赖和配置。
    """

    # 必填字段
    type: str  # 扩展类型
    id: str  # 唯一标识（如 "openai-adapter", "emotional_comfort"）
    name: str  # 显示名称
    version: str  # 语义化版本号

    # 可选字段
    description: str = ""
    author: str = ""
    license: str = "MIT"
    homepage: str = ""
    repository: str = ""
    schema_version: str = MANIFEST_SCHEMA_VERSION

    # 依赖
    dependencies: list[str] = field(default_factory=list)  # 其他扩展 ID
    python_requires: str = ">=3.12"
    python_packages: list[str] = field(default_factory=list)  # pip 依赖

    # 元数据
    capability_tags: list[str] = field(default_factory=list)
    category: str = ""
    supported_models: list[str] = field(default_factory=list)  # 仅 AI Provider
    platform: str = ""  # 仅 Channel
    permission_level: str = "safe"  # 仅 Tool: safe/restricted/dangerous

    # 配置
    config_schema: dict[str, Any] = field(default_factory=dict)  # JSON Schema
    default_config: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        """验证 manifest 合规性

        Returns:
            错误列表，空表示验证通过
        """
        errors: list[str] = []

        # 必填字段检查
        if not self.type:
            errors.append("Missing required field: type")
        elif self.type not in EXTENSION_TYPES:
            errors.append(
                f"Invalid type: {self.type}. "
                f"Must be one of {list(EXTENSION_TYPES.keys())}"
            )

        if not self.id:
            errors.append("Missing required field: id")
        if not self.name:
            errors.append("Missing required field: name")
        if not self.version:
            errors.append("Missing required field: version")

        # 类型特定检查
        if self.type == "ai_provider":
            if not self.supported_models:
                errors.append("AI provider must declare supported_models")

        if self.type == "channel":
            if not self.platform:
                errors.append("Channel must declare platform")

        if self.type == "tool":
            if self.permission_level not in ("safe", "restricted", "dangerous"):
                errors.append(f"Invalid permission_level: {self.permission_level}")

        # 版本号格式检查
        if self.version:
            try:
                parsed = parse_version(self.version)
                if len(parsed) < 2:
                    errors.append(
                        f"Version '{self.version}' should have at least major.minor format"
                    )
            except Exception:
                errors.append(f"Invalid version format: {self.version}")

        # 依赖版本格式检查
        for dep in self.dependencies:
            if ":" in dep:
                _, dep_version = dep.rsplit(":", 1)
                try:
                    parse_version(dep_version)
                except Exception:
                    errors.append(f"Invalid dependency version format: {dep}")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "schema_version": self.schema_version,
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "homepage": self.homepage,
            "repository": self.repository,
            "dependencies": self.dependencies,
            "python_requires": self.python_requires,
            "python_packages": self.python_packages,
            "capability_tags": self.capability_tags,
            "category": self.category,
            "supported_models": self.supported_models,
            "platform": self.platform,
            "permission_level": self.permission_level,
            "config_schema": self.config_schema,
            "default_config": self.default_config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtensionManifest:
        """从字典创建"""
        return cls(
            type=data.get("type", ""),
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", ""),
            description=data.get("description", ""),
            author=data.get("author", ""),
            license=data.get("license", "MIT"),
            homepage=data.get("homepage", ""),
            repository=data.get("repository", ""),
            schema_version=data.get("schema_version", MANIFEST_SCHEMA_VERSION),
            dependencies=data.get("dependencies", []),
            python_requires=data.get("python_requires", ">=3.12"),
            python_packages=data.get("python_packages", []),
            capability_tags=data.get("capability_tags", []),
            category=data.get("category", ""),
            supported_models=data.get("supported_models", []),
            platform=data.get("platform", ""),
            permission_level=data.get("permission_level", "safe"),
            config_schema=data.get("config_schema", {}),
            default_config=data.get("default_config", {}),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> ExtensionManifest:
        """从 manifest.json 文件加载"""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


class VersionManager:
    """扩展版本管理器

    管理扩展的版本检查、兼容性验证和更新检测。
    """

    @staticmethod
    def check_dependencies(
        manifest: ExtensionManifest,
        installed_extensions: dict[str, str],
    ) -> list[str]:
        """检查扩展依赖是否满足

        Args:
            manifest: 扩展清单
            installed_extensions: 已安装扩展 {id: version}

        Returns:
            错误列表（空表示依赖满足）
        """
        errors: list[str] = []
        for dep in manifest.dependencies:
            if ":" in dep:
                dep_id, required_version = dep.rsplit(":", 1)
            else:
                dep_id = dep
                required_version = ""

            if dep_id not in installed_extensions:
                errors.append(f"Missing dependency: {dep_id}")
                continue

            if required_version:
                available = installed_extensions[dep_id]
                if not is_version_compatible(required_version, available):
                    errors.append(
                        f"Dependency version mismatch: {dep_id} "
                        f"requires {required_version}, "
                        f"got {available}"
                    )

        return errors

    @staticmethod
    def check_update_available(
        current_version: str,
        latest_version: str,
    ) -> bool:
        """检查是否有可用更新

        Args:
            current_version: 当前版本
            latest_version: 最新版本

        Returns:
            是否有更新
        """
        return compare_versions(latest_version, current_version) > 0


class ExtensionValidator:
    """扩展合规性验证器

    验证扩展包是否符合 Y.E.S. 规范。

    设计参考: development-standards-ecosystem.md 9.1
    """

    @staticmethod
    def validate_extension_dir(extension_dir: str | Path) -> list[str]:
        """验证扩展目录结构

        Args:
            extension_dir: 扩展目录路径

        Returns:
            错误列表
        """
        errors: list[str] = []
        ext_path = Path(extension_dir)

        if not ext_path.exists():
            errors.append(f"Extension directory does not exist: {ext_path}")
            return errors

        # 检查 manifest.json
        manifest_path = ext_path / "manifest.json"
        if not manifest_path.exists():
            errors.append("Missing manifest.json")
            return errors

        # 加载并验证 manifest
        try:
            manifest = ExtensionManifest.from_file(manifest_path)
            errors.extend(manifest.validate())
        except Exception as e:
            errors.append(f"Failed to parse manifest.json: {e}")
            return errors

        # 检查必要文件
        if manifest.type == "ai_provider":
            if not (ext_path / "adapter.py").exists():
                errors.append("AI provider extension must contain adapter.py")

        elif manifest.type == "channel":
            if not (ext_path / "adapter.py").exists():
                errors.append("Channel extension must contain adapter.py")

        elif manifest.type == "skill":
            if not (ext_path / "definition.yaml").exists():
                errors.append("Skill extension must contain definition.yaml")

        elif manifest.type == "tool":
            has_schema = (ext_path / "schema.json").exists()
            has_executor = (ext_path / "executor.py").exists()
            has_dockerfile = (ext_path / "Dockerfile").exists()
            if not has_schema:
                errors.append("Tool extension must contain schema.json")
            if not has_executor and not has_dockerfile:
                errors.append("Tool extension must contain executor.py or Dockerfile")

        elif manifest.type == "persona":
            if not (ext_path / "persona.yaml").exists():
                errors.append("Persona extension must contain persona.yaml")

        # 检查 README
        if not (ext_path / "README.md").exists():
            errors.append("Extension should contain README.md (recommended)")

        return errors

    @staticmethod
    def validate_interface_compliance(
        manifest: ExtensionManifest,
        implementation_check: dict[str, bool],
    ) -> list[str]:
        """验证接口合规性

        Args:
            manifest: 扩展清单
            implementation_check: 接口实现检查结果
                {"method_name": True/False}

        Returns:
            缺失的接口方法列表
        """
        errors: list[str] = []

        # AI Provider 必须实现的方法
        ai_provider_methods = [
            "chat_completion",
            "stream_chat_completion",
            "get_embedding",
            "supported_models",
            "max_context_length",
            "provider_id",
        ]

        # Channel 必须实现的方法
        channel_methods = [
            "initialize",
            "listen",
            "send_message",
            "get_platform_user_id",
            "platform_name",
            "supported_content_types",
        ]

        required_methods: list[str] = []
        if manifest.type == "ai_provider":
            required_methods = ai_provider_methods
        elif manifest.type == "channel":
            required_methods = channel_methods

        errors.extend(
            f"Missing required method: {method}"
            for method in required_methods
            if not implementation_check.get(method, False)
        )

        return errors


def create_scaffold(
    extension_type: str,
    extension_id: str,
    output_dir: str | Path,
) -> Path:
    """创建扩展脚手架

    Args:
        extension_type: 扩展类型
        extension_id: 扩展 ID
        output_dir: 输出目录

    Returns:
        创建的扩展目录路径
    """
    if extension_type not in EXTENSION_TYPES:
        raise ValueError(f"Invalid extension type: {extension_type}")

    ext_dir = Path(output_dir) / f"yuanbot-{extension_type}-{extension_id}"
    ext_dir.mkdir(parents=True, exist_ok=True)

    # 创建 manifest.json
    manifest = ExtensionManifest(
        type=extension_type,
        id=extension_id,
        name=extension_id.replace("_", " ").title(),
        version="1.0.0",
        description=f"YuanBot {EXTENSION_TYPES[extension_type]}: {extension_id}",
        author="community",
    )
    with open(ext_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)

    # 创建类型特定文件
    if extension_type == "ai_provider":
        _create_ai_provider_scaffold(ext_dir, extension_id)
    elif extension_type == "channel":
        _create_channel_scaffold(ext_dir, extension_id)
    elif extension_type == "skill":
        _create_skill_scaffold(ext_dir, extension_id)
    elif extension_type == "tool":
        _create_tool_scaffold(ext_dir, extension_id)
    elif extension_type == "persona":
        _create_persona_scaffold(ext_dir, extension_id)

    # 创建 README
    with open(ext_dir / "README.md", "w", encoding="utf-8") as f:
        f.write(f"# {manifest.name}\n\n{manifest.description}\n\n## Installation\n\nTODO\n")

    logger.info("scaffold_created", path=str(ext_dir), type=extension_type)
    return ext_dir


def _create_ai_provider_scaffold(ext_dir: Path, provider_id: str) -> None:
    """创建 AI 提供商适配器脚手架"""
    class_name = provider_id.replace("_", " ").title().replace(" ", "") + "Adapter"
    with open(ext_dir / "adapter.py", "w", encoding="utf-8") as f:
        f.write(f'''"""YuanBot AI Provider: {provider_id}"""

from yuanbot.core.interfaces import AIProviderAdapter
from yuanbot.core.types import ChatResponse, ChatChunk, Message, ToolDefinition


class {class_name}(AIProviderAdapter):
    """{provider_id} AI 提供商适配器"""

    def __init__(self, config: dict):
        self._config = config

    async def chat_completion(self, messages, tools=None, temperature=0.7,
                               max_tokens=4096, system_prompt=None):
        raise NotImplementedError

    async def stream_chat_completion(self, messages, tools=None, temperature=0.7,
                                      max_tokens=4096, system_prompt=None):
        raise NotImplementedError
        yield  # pragma: no cover

    async def get_embedding(self, text, model=None):
        raise NotImplementedError

    @property
    def supported_models(self):
        return []

    @property
    def max_context_length(self):
        return 128000

    @property
    def provider_id(self):
        return "{provider_id}"
''')


def _create_channel_scaffold(ext_dir: Path, platform: str) -> None:
    """创建消息通道适配器脚手架"""
    class_name = platform.replace("_", " ").title().replace(" ", "") + "Adapter"
    with open(ext_dir / "adapter.py", "w", encoding="utf-8") as f:
        f.write(f'''"""YuanBot Channel: {platform}"""

from yuanbot.core.interfaces import ChannelAdapter
from yuanbot.core.types import ChannelConfig, UserMessage, MessageContent, SendResult, ContentType


class {class_name}(ChannelAdapter):
    """{platform} 通道适配器"""

    def __init__(self):
        self._config = None

    async def initialize(self, config: ChannelConfig) -> None:
        self._config = config

    async def listen(self, callback):
        raise NotImplementedError

    async def send_message(self, target_id: str, content: MessageContent) -> SendResult:
        raise NotImplementedError

    def get_platform_user_id(self, raw_event) -> str:
        raise NotImplementedError

    @property
    def platform_name(self) -> str:
        return "{platform}"

    @property
    def supported_content_types(self):
        return [ContentType.TEXT]
''')


def _create_skill_scaffold(ext_dir: Path, skill_id: str) -> None:
    """创建技能脚手架"""
    import yaml

    skill_config = {
        "skill_id": skill_id,
        "name": skill_id.replace("_", " ").title(),
        "version": "1.0.0",
        "enabled": True,
        "category": "utility",
        "capability_tags": [],
        "token_cost_estimate": 200,
        "prompt_template": f"[技能：{skill_id}]\nTODO: 定义技能提示词",
    }
    with open(ext_dir / "definition.yaml", "w", encoding="utf-8") as f:
        yaml.dump(skill_config, f, allow_unicode=True, default_flow_style=False)


def _create_tool_scaffold(ext_dir: Path, tool_id: str) -> None:
    """创建工具脚手架"""
    schema = {
        "type": "function",
        "function": {
            "name": tool_id,
            "description": f"{tool_id} 工具描述",
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "输入参数",
                    }
                },
                "required": ["input"],
            },
        },
    }
    with open(ext_dir / "schema.json", "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    with open(ext_dir / "executor.py", "w", encoding="utf-8") as f:
        f.write(f'''"""YuanBot Tool: {tool_id}"""

from typing import Any


async def execute(params: dict[str, Any]) -> dict[str, Any]:
    """执行工具

    Args:
        params: 工具参数

    Returns:
        执行结果
    """
    # TODO: 实现工具逻辑
    return {{"result": "TODO", "params": params}}
''')


def _create_persona_scaffold(ext_dir: Path, persona_id: str) -> None:
    """创建人设包脚手架"""
    import yaml

    persona_config = {
        "persona_id": persona_id,
        "name": persona_id.replace("_", " ").title(),
        "version": "1.0.0",
        "description": f"{persona_id} 人设描述",
        "voice_style": {
            "tone": "友好",
            "speech_pattern": "自然",
        },
        "behavior_rules": [
            "保持友好",
        ],
        "capability_domains": [
            "daily_chat",
        ],
        "emotional_profile": {
            "baseline_mood": "cheerful",
            "empathy": 0.8,
        },
    }
    with open(ext_dir / "persona.yaml", "w", encoding="utf-8") as f:
        yaml.dump(persona_config, f, allow_unicode=True, default_flow_style=False)
