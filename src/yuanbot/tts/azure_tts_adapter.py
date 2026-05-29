"""Azure Cognitive Services Speech TTS 适配器

微软官方 TTS 引擎，音色库最丰富，神经语音质量极高，
支持 SSML 精细控制（语速、音调、停顿、强调等）。

需要 Azure 订阅和 Speech 资源。
设计参考: docs/tts-system.md 5.4节
"""

from __future__ import annotations

import asyncio
import logging
import os
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
    VoiceInfo("zh-CN-XiaohanNeural", "晓涵（女·温暖）", "zh-CN", "female"),
    VoiceInfo("zh-CN-XiaomengNeural", "晓梦（女·甜美）", "zh-CN", "female"),
    VoiceInfo("zh-CN-XiaomoNeural", "晓墨（女·文艺）", "zh-CN", "female"),
    VoiceInfo("zh-CN-XiaoqiuNeural", "晓秋（女·成熟）", "zh-CN", "female"),
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


def _rate_to_ssml(rate: float) -> str:
    """将语速倍率转换为 SSML rate 属性"""
    pct = int((rate - 1.0) * 100)
    if pct == 0:
        return "medium"
    return f"{pct:+d}%"


def _pitch_to_ssml(pitch: float) -> str:
    """将音调倍率转换为 SSML pitch 属性"""
    pct = int((pitch - 1.0) * 100)
    if pct == 0:
        return "medium"
    return f"{pct:+d}%"


class AzureTTSAdapter(TTSAdapter):
    """Azure Cognitive Services Speech TTS 适配器

    特点：
    - 微软官方，音色库最丰富
    - 神经语音质量极高
    - 支持 SSML 精细控制
    - 需要 Azure 订阅和 Speech 资源
    """

    def __init__(
        self,
        subscription_key: str | None = None,
        region: str = "eastus",
        default_voice: str = "zh-CN-XiaoxiaoNeural",
    ) -> None:
        self._subscription_key = subscription_key or os.environ.get(
            "AZURE_SPEECH_KEY", ""
        )
        self._region = region or os.environ.get("AZURE_SPEECH_REGION", "eastus")
        self._default_voice = default_voice
        self._available: bool | None = None

    @property
    def engine_id(self) -> str:
        return "azure"

    def _build_ssml(
        self,
        text: str,
        voice: str,
        rate: float = 1.0,
        pitch: float = 1.0,
    ) -> str:
        """构建 SSML 请求体"""
        rate_str = _rate_to_ssml(rate)
        pitch_str = _pitch_to_ssml(pitch)

        return f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
       xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='zh-CN'>
  <voice name='{voice}'>
    <prosody rate='{rate_str}' pitch='{pitch_str}'>
      {text}
    </prosody>
  </voice>
</speak>"""

    async def _get_access_token(self) -> str:
        """获取 Azure Speech 访问令牌"""
        import urllib.parse
        import urllib.request

        url = f"https://{self._region}.api.cognitive.microsoft.com/sts/v1.0/issuetoken"
        headers = {
            "Ocp-Apim-Subscription-Key": self._subscription_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        req = urllib.request.Request(url, data=b"", headers=headers, method="POST")
        response = await asyncio.to_thread(urllib.request.urlopen, req, timeout=10)
        return response.read().decode("utf-8")

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: float = 1.0,
        pitch: float = 1.0,
        output_format: str = "mp3",
    ) -> bytes:
        """非流式合成，返回完整音频字节"""
        if not self._subscription_key:
            raise RuntimeError(
                "Azure Speech subscription key not configured. "
                "Set AZURE_SPEECH_KEY environment variable or pass subscription_key."
            )

        try:
            token = await self._get_access_token()
            ssml = self._build_ssml(text, voice, rate, pitch)

            url = (
                f"https://{self._region}.tts.speech.microsoft.com/"
                "cognitiveservices/v1"
            )
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": self._map_output_format(output_format),
                "User-Agent": "YuanBot",
            }

            audio_bytes = await asyncio.to_thread(
                self._http_post, url, ssml.encode("utf-8"), headers
            )
            return audio_bytes

        except Exception as e:
            logger.error("azure_tts_synthesize_failed", error=str(e))
            raise

    def _http_post(self, url: str, data: bytes, headers: dict[str, str]) -> bytes:
        """同步 HTTP POST（在线程池中运行）"""
        import urllib.request

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        response = urllib.request.urlopen(req, timeout=30)
        return response.read()

    async def synthesize_stream(
        self,
        text: str,
        voice: str,
        rate: float = 1.0,
        pitch: float = 1.0,
        output_format: str = "mp3",
    ) -> AsyncIterator[bytes]:
        """流式合成

        Azure TTS 支持流式输出。按句子分句后逐段合成。
        """
        if not self._subscription_key:
            raise RuntimeError("Azure Speech subscription key not configured.")

        sentences = self._split_sentences(text)
        for sentence in sentences:
            if not sentence.strip():
                continue
            try:
                chunk = await self.synthesize(
                    sentence, voice, rate, pitch, output_format
                )
                yield chunk
            except Exception as e:
                logger.warning(
                    "azure_tts_stream_chunk_failed",
                    sentence=sentence,
                    error=str(e),
                )
                continue

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """按句末标点分句"""
        import re

        parts = re.split(r"([。！？!?；;\n])", text)
        sentences: list[str] = []
        current = ""
        for part in parts:
            current += part
            if part in ("。", "！", "？", "!", "?", "；", ";", "\n"):
                sentences.append(current)
                current = ""
        if current.strip():
            sentences.append(current)
        return sentences

    @staticmethod
    def _map_output_format(fmt: str) -> str:
        """映射简写格式到 Azure 完整格式名"""
        mapping = {
            "mp3": "audio-24khz-96kbitrate-mono-mp3",
            "wav": "riff-24khz-16bit-mono-pcm",
            "ogg": "ogg-24khz-16bit-mono-opus",
        }
        return mapping.get(fmt, fmt)

    def list_voices(self) -> list[VoiceInfo]:
        """返回常用中文音色列表"""
        return _CHINESE_VOICES.copy()

    async def is_available(self) -> bool:
        """检查引擎是否可用"""
        if self._available is not None:
            return self._available
        self._available = bool(self._subscription_key)
        return self._available
