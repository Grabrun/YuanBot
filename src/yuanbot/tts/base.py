"""TTS 适配器抽象接口"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class VoiceInfo:
    """音色信息"""

    id: str
    name: str
    language: str = "zh-CN"
    gender: str = "female"  # "male" | "female" | "neutral"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "language": self.language,
            "gender": self.gender,
        }


class TTSAdapter(ABC):
    """TTS 引擎统一接口

    所有 TTS 引擎（Edge-TTS、Piper、OpenAI TTS、Azure TTS 等）
    都必须实现此接口。
    """

    @property
    @abstractmethod
    def engine_id(self) -> str:
        """引擎唯一标识（如 'edge-tts', 'openai', 'piper'）"""
        ...

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: float = 1.0,
        pitch: float = 1.0,
        output_format: str = "mp3",
    ) -> bytes:
        """非流式合成，返回完整音频字节

        Args:
            text: 待合成文本
            voice: 音色 ID
            rate: 语速倍率 (0.5 ~ 2.0)
            pitch: 音调倍率 (0.5 ~ 2.0)
            output_format: 输出格式 ("mp3", "wav", "ogg")

        Returns:
            完整音频字节
        """
        ...

    @abstractmethod
    async def synthesize_stream(
        self,
        text: str,
        voice: str,
        rate: float = 1.0,
        pitch: float = 1.0,
        output_format: str = "mp3",
    ) -> AsyncIterator[bytes]:
        """流式合成，返回音频字节块异步迭代器

        Args:
            text: 待合成文本
            voice: 音色 ID
            rate: 语速倍率
            pitch: 音调倍率
            output_format: 输出格式

        Yields:
            音频字节块
        """
        ...

    @abstractmethod
    def list_voices(self) -> list[VoiceInfo]:
        """返回该引擎支持的音色列表"""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """检查引擎是否可用（网络连通、本地模型存在等）"""
        ...

    def get_default_voice(self) -> str:
        """返回该引擎的默认音色 ID"""
        voices = self.list_voices()
        if voices:
            return voices[0].id
        return ""
