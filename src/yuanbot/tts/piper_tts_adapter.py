"""Piper TTS 适配器 — 本地离线 TTS 引擎

基于 piper-tts 库，完全本地运行，无需网络连接。
需提前下载语音模型到 model_dir 目录。

设计参考: docs/tts-system.md 5.2节
"""

from __future__ import annotations

import asyncio
import logging
import struct
from collections.abc import AsyncIterator
from pathlib import Path

from yuanbot.tts.base import TTSAdapter, VoiceInfo

logger = logging.getLogger(__name__)

# 内置中文音色列表
_CHINESE_VOICES = [
    VoiceInfo("zh_CN-huayan-medium", "华燕（女·温和）", "zh-CN", "female"),
    VoiceInfo("zh_CN-ljspeech-medium", "LJSpeech（女·清晰）", "zh-CN", "female"),
    VoiceInfo("zh_CN-huayan-medium-fast", "华燕快速（女·温和）", "zh-CN", "female"),
]


class PiperTTSAdapter(TTSAdapter):
    """Piper TTS 本地离线引擎适配器

    特点：
    - 完全本地离线，无网络依赖
    - 隐私性强，文本不离开本机
    - 需提前下载语音模型（200-400 MB）
    - 推理速度快（CPU 即可）
    """

    def __init__(
        self,
        model_dir: str = "data/piper_models",
        default_voice: str = "zh_CN-huayan-medium",
        length_scale: float = 1.0,
        sentence_silence: float = 0.2,
    ) -> None:
        self._model_dir = Path(model_dir)
        self._default_voice = default_voice
        self._length_scale = length_scale
        self._sentence_silence = sentence_silence
        self._model = None
        self._synthesizer = None
        self._available = False

    @property
    def engine_id(self) -> str:
        return "piper"

    async def _ensure_model(self, voice: str) -> bool:
        """懒加载模型：首次调用时加载，避免启动延迟"""
        if self._synthesizer is not None and self._model is not None:
            return True

        try:
            from piper import PiperVoice  # type: ignore[import-untyped]

            model_path = self._model_dir / f"{voice}.onnx"
            if not model_path.exists():
                logger.error(
                    "piper_model_not_found",
                    voice=voice,
                    path=str(model_path),
                )
                return False

            self._model = PiperVoice.load(str(model_path))
            self._synthesizer = self._model.synthesize_stream_raw
            self._available = True
            logger.info("piper_model_loaded", voice=voice)
            return True

        except ImportError:
            logger.warning("piper_not_installed: pip install piper-tts")
            return False
        except Exception as e:
            logger.error("piper_model_load_failed", error=str(e))
            return False

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: float = 1.0,
        pitch: float = 1.0,
        output_format: str = "wav",
    ) -> bytes:
        """非流式合成，返回完整音频字节

        Args:
            text: 待合成文本
            voice: 音色 ID (如 'zh_CN-huayan-medium')
            rate: 语速倍率 (0.5 ~ 2.0)
            pitch: 音调倍率 (Piper 不直接支持，忽略)
            output_format: 输出格式 ('wav' 或 'raw')

        Returns:
            完整音频字节 (WAV 格式)
        """
        if not await self._ensure_model(voice):
            raise RuntimeError(f"Piper TTS 引擎不可用，voice={voice}")

        # 语速调整：length_scale 越大越慢
        length_scale = self._length_scale / max(0.5, min(2.0, rate))

        try:
            # Piper 合成在同步线程中运行，使用 asyncio.to_thread 避免阻塞
            audio_bytes = await asyncio.to_thread(
                self._synthesize_sync,
                text,
                voice,
                length_scale,
                output_format,
            )
            return audio_bytes
        except Exception as e:
            logger.error("piper_synthesize_failed", error=str(e))
            raise

    def _synthesize_sync(
        self,
        text: str,
        voice: str,
        length_scale: float,
        output_format: str,
    ) -> bytes:
        """同步合成（在线程池中运行）"""
        assert self._model is not None

        # 收集所有音频 chunk
        audio_chunks: list[bytes] = []
        for chunk in self._model.synthesize_stream_raw(
            text,
            length_scale=length_scale,
            sentence_silence=self._sentence_silence,
        ):
            audio_chunks.append(chunk)

        raw_audio = b"".join(audio_chunks)

        if output_format == "wav":
            return self._raw_to_wav(raw_audio, self._model.config.sample_rate)
        return raw_audio

    @staticmethod
    def _raw_to_wav(raw_pcm: bytes, sample_rate: int) -> bytes:
        """将原始 PCM 数据包装为 WAV 格式"""
        num_channels = 1
        bits_per_sample = 16
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_size = len(raw_pcm)

        # WAV header (44 bytes)
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            36 + data_size,
            b"WAVE",
            b"fmt ",
            16,  # chunk size
            1,  # PCM format
            num_channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
            b"data",
            data_size,
        )
        return header + raw_pcm

    async def synthesize_stream(
        self,
        text: str,
        voice: str,
        rate: float = 1.0,
        pitch: float = 1.0,
        output_format: str = "wav",
    ) -> AsyncIterator[bytes]:
        """流式合成，按句子分块输出

        将文本按句号/感叹号/问号分句，逐句合成并 yield。
        """
        if not await self._ensure_model(voice):
            raise RuntimeError(f"Piper TTS 引擎不可用，voice={voice}")

        length_scale = self._length_scale / max(0.5, min(2.0, rate))

        # 按句末标点分句
        sentences = self._split_sentences(text)

        for sentence in sentences:
            if not sentence.strip():
                continue
            try:
                chunk = await asyncio.to_thread(
                    self._synthesize_sync,
                    sentence,
                    voice,
                    length_scale,
                    output_format,
                )
                yield chunk
            except Exception as e:
                logger.warning("piper_stream_chunk_failed", sentence=sentence, error=str(e))
                continue

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """按句末标点分句"""
        import re

        # 匹配中文和英文句末标点
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

    def list_voices(self) -> list[VoiceInfo]:
        """返回内置中文音色列表

        实际可用音色取决于 model_dir 中的模型文件。
        """
        available_voices = []
        if self._model_dir.exists():
            for onnx_file in self._model_dir.glob("*.onnx"):
                voice_id = onnx_file.stem
                # 尝试匹配内置列表
                matched = [v for v in _CHINESE_VOICES if v.id == voice_id]
                if matched:
                    available_voices.append(matched[0])
                else:
                    available_voices.append(
                        VoiceInfo(voice_id, voice_id, "zh-CN", "female")
                    )
        if not available_voices:
            # 模型目录不存在时返回内置列表
            return _CHINESE_VOICES.copy()
        return available_voices

    async def is_available(self) -> bool:
        """检查引擎是否可用（piper 库已安装且模型存在）"""
        try:
            import importlib.util

            if importlib.util.find_spec("piper") is None:
                return False

            # 检查默认模型是否存在
            model_path = self._model_dir / f"{self._default_voice}.onnx"
            return model_path.exists()
        except Exception:
            return False
