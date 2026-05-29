"""OpenAI TTS 适配器"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator

from yuanbot.tts.base import TTSAdapter, VoiceInfo

logger = logging.getLogger(__name__)

_OPENAI_VOICES = [
    VoiceInfo("alloy", "Alloy（中性·平衡）", "multi", "neutral"),
    VoiceInfo("echo", "Echo（男·低沉）", "multi", "male"),
    VoiceInfo("fable", "Fable（男·英式）", "multi", "male"),
    VoiceInfo("onyx", "Onyx（男·深沉）", "multi", "male"),
    VoiceInfo("nova", "Nova（女·温暖）", "multi", "female"),
    VoiceInfo("shimmer", "Shimmer（女·明亮）", "multi", "female"),
]


class OpenAITTSAdapter(TTSAdapter):
    """OpenAI TTS 适配器

    使用 OpenAI tts-1 或 tts-1-hd 模型。
    需安装: pip install openai
    需配置: OPENAI_API_KEY 环境变量
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "tts-1",
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._model = model
        self._base_url = base_url
        self._available: bool | None = None

    @property
    def engine_id(self) -> str:
        return "openai"

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: float = 1.0,
        pitch: float = 1.0,
        output_format: str = "mp3",
    ) -> bytes:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )

        # OpenAI TTS 不支持 rate/pitch 直接调整，通过 prompt 前缀近似
        response = await client.audio.speech.create(
            model=self._model,
            voice=voice,
            input=text,
            response_format=output_format if output_format != "wav" else "pcm",
        )

        return response.content

    async def synthesize_stream(
        self,
        text: str,
        voice: str,
        rate: float = 1.0,
        pitch: float = 1.0,
        output_format: str = "mp3",
    ) -> AsyncIterator[bytes]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )

        async with client.audio.speech.with_streaming_response.create(
            model=self._model,
            voice=voice,
            input=text,
            response_format=output_format if output_format != "wav" else "pcm",
        ) as response:
            async for chunk in response.iter_bytes(chunk_size=4096):
                if chunk:
                    yield chunk

    def list_voices(self) -> list[VoiceInfo]:
        return list(_OPENAI_VOICES)

    async def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        if not self._api_key:
            self._available = False
            return False
        try:
            from openai import AsyncOpenAI  # noqa: F401

            self._available = True
        except ImportError:
            logger.warning("openai 未安装，请运行: pip install openai")
            self._available = False
        return self._available
