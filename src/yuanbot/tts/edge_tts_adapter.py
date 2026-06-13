"""Edge-TTS 适配器 — Microsoft Edge 免费 TTS"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from yuanbot.tts.base import TTSAdapter, VoiceInfo

logger = logging.getLogger(__name__)

# 常用中文音色
_CHINESE_VOICES = [
    VoiceInfo("zh-CN-XiaoxiaoNeural", "晓晓（女·活泼）", "zh-CN", "female"),
    VoiceInfo("zh-CN-YunxiNeural", "云希（男·稳重）", "zh-CN", "male"),
    VoiceInfo("zh-CN-XiaoyiNeural", "晓伊（女·温柔）", "zh-CN", "female"),
    VoiceInfo("zh-CN-YunjianNeural", "云健（男·阳刚）", "zh-CN", "male"),
    VoiceInfo("zh-CN-XiaochenNeural", "晓辰（女·知性）", "zh-CN", "female"),
    VoiceInfo("zh-CN-XiaomengNeural", "晓梦（女·甜美）", "zh-CN", "female"),
    VoiceInfo("zh-CN-XiaomoNeural", "晓墨（女·文艺）", "zh-CN", "female"),
    VoiceInfo("zh-CN-XiaoruiNeural", "晓睿（女·成熟）", "zh-CN", "female"),
    VoiceInfo("zh-CN-XiaoshuangNeural", "晓双（女·童声）", "zh-CN", "female"),
    VoiceInfo("zh-CN-XiaoxuanNeural", "晓萱（女·活力）", "zh-CN", "female"),
    VoiceInfo("zh-CN-XiaoyanNeural", "晓颜（女·亲和）", "zh-CN", "female"),
    VoiceInfo("zh-CN-XiaozhenNeural", "晓甄（女·正式）", "zh-CN", "female"),
    VoiceInfo("zh-CN-YunyangNeural", "云扬（男·新闻）", "zh-CN", "male"),
    VoiceInfo("zh-CN-YunxiaNeural", "云夏（男·少年）", "zh-CN", "male"),
    VoiceInfo("zh-CN-YunyeNeural", "云野（男·文艺）", "zh-CN", "male"),
    VoiceInfo("zh-CN-YunzeNeural", "云泽（男·成熟）", "zh-CN", "male"),
]


def _rate_to_str(rate: float) -> str:
    """将语速倍率转换为 edge-tts 的 rate 字符串（如 '+0%', '-10%'）"""
    pct = int((rate - 1.0) * 100)
    return f"{pct:+d}%"


def _pitch_to_str(pitch: float) -> str:
    """将音调倍率转换为 edge-tts 的 pitch 字符串（如 '+0Hz', '-5Hz'）"""
    hz = int((pitch - 1.0) * 50)
    return f"{hz:+d}Hz"


class EdgeTTSAdapter(TTSAdapter):
    """Microsoft Edge TTS 适配器

    使用 edge-tts 库，免费、中文自然度高、无需 API Key。
    需安装: pip install edge-tts
    """

    def __init__(self) -> None:
        self._available: bool | None = None

    @property
    def engine_id(self) -> str:
        return "edge-tts"

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: float = 1.0,
        pitch: float = 1.0,
        output_format: str = "mp3",
    ) -> bytes:
        import edge_tts

        rate_str = _rate_to_str(rate)
        pitch_str = _pitch_to_str(pitch)

        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate_str,
            pitch=pitch_str,
        )

        audio_chunks = [
            chunk["data"]
            async for chunk in communicate.stream()
            if chunk["type"] == "audio"
        ]

        return b"".join(audio_chunks)

    async def synthesize_stream(
        self,
        text: str,
        voice: str,
        rate: float = 1.0,
        pitch: float = 1.0,
        output_format: str = "mp3",
    ) -> AsyncIterator[bytes]:
        import edge_tts

        rate_str = _rate_to_str(rate)
        pitch_str = _pitch_to_str(pitch)

        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate_str,
            pitch=pitch_str,
        )

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    def list_voices(self) -> list[VoiceInfo]:
        return list(_CHINESE_VOICES)

    async def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import importlib.util
            if importlib.util.find_spec("edge_tts"):
                self._available = True
            else:
                logger.warning("edge-tts 未安装，请运行: pip install edge-tts")
                self._available = False
        except Exception:
            logger.warning("edge-tts 检查失败")
            self._available = False
        return self._available
