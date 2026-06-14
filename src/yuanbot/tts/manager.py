"""TTS 管理器 — 引擎选择、缓存、流式合成、流式缓冲区"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yuanbot.tts.base import TTSAdapter, VoiceInfo

logger = logging.getLogger(__name__)


@dataclass
class TTSCacheConfig:
    """TTS 缓存配置"""

    memory_size: int = 100  # L1 内存缓存条目数
    file_cache_path: str = "data/tts_cache"  # L2 文件缓存目录
    file_cache_max_mb: int = 500  # L2 文件缓存上限 (MB)


@dataclass
class TTSConfig:
    """TTS 全局配置"""

    enabled: bool = True
    default_engine: str = "edge-tts"
    default_voice: str = "zh-CN-XiaoxiaoNeural"
    streaming: bool = True
    cache: TTSCacheConfig = field(default_factory=TTSCacheConfig)


class TTSCache:
    """双层音频缓存 (L1 内存 + L2 文件)"""

    # Eviction frequency: only scan files every N puts to avoid repeated stat calls
    _EVICTION_INTERVAL = 20

    def __init__(self, config: TTSCacheConfig) -> None:
        self._config = config
        self._memory: OrderedDict[str, bytes] = OrderedDict()
        self._put_count: int = 0  # Track put() calls for lazy eviction
        self._file_dir = Path(config.file_cache_path)
        self._file_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _make_key(engine: str, voice: str, text: str) -> str:
        """生成缓存键: sha256(engine|voice|text[:200])"""
        content = f"{engine}|{voice}|{text[:200]}"
        return hashlib.sha256(content.encode()).hexdigest()

    def get(
        self,
        engine: str,
        voice: str,
        text: str,
        user_id: str | None = None,
    ) -> bytes | None:
        """查询缓存，优先 L1 内存

        设计参考: tts-system.md 第12节 - 音频缓存隔离：
        不同用户的音频缓存文件通过用户 ID 划分目录。
        """
        key = self._make_key(engine, voice, text)

        # L1: 内存
        if key in self._memory:
            self._memory.move_to_end(key)
            return self._memory[key]

        # L2: 文件 (按用户 ID 隔离目录)
        cache_dir = self._get_user_cache_dir(user_id)
        file_path = cache_dir / f"{key}.audio"
        if file_path.exists():
            try:
                data = file_path.read_bytes()
                self._put_memory(key, data)
                return data
            except OSError:
                pass

        return None

    def put(
        self,
        engine: str,
        voice: str,
        text: str,
        audio: bytes,
        user_id: str | None = None,
    ) -> None:
        """写入缓存 (L1 + L2)

        L2 文件按用户 ID 划分目录，防止越权访问。
        """
        key = self._make_key(engine, voice, text)

        # L1
        self._put_memory(key, audio)

        # L2 (按用户 ID 隔离目录)
        try:
            cache_dir = self._get_user_cache_dir(user_id)
            file_path = cache_dir / f"{key}.audio"
            file_path.write_bytes(audio)
            self._put_count += 1
            if self._put_count % self._EVICTION_INTERVAL == 0:
                self._evict_file_cache()
        except OSError as e:
            logger.warning("TTS 文件缓存写入失败: %s", e)

    def _get_user_cache_dir(self, user_id: str | None) -> Path:
        """获取用户级缓存目录

        未指定用户时使用共享目录；指定时使用 user_id 子目录。
        """
        if user_id:
            # 对 user_id 做安全过滤，防止路径穿越
            safe_id = "".join(c for c in user_id if c.isalnum() or c in "-_")
            if safe_id:
                user_dir = self._file_dir / safe_id
                user_dir.mkdir(parents=True, exist_ok=True)
                return user_dir
        return self._file_dir

    def _put_memory(self, key: str, data: bytes) -> None:
        """写入 L1 内存缓存"""
        if key in self._memory:
            self._memory.move_to_end(key)
        else:
            if len(self._memory) >= self._config.memory_size:
                self._memory.popitem(last=False)
            self._memory[key] = data

    def _evict_file_cache(self) -> None:
        """L2 文件缓存淘汰：按时间排序，超出容量上限时删除最旧文件

        遍历所有用户子目录，按访问时间全局排序淘汰。
        使用 os.scandir + 缓存 stat 结果，避免重复系统调用。
        """
        import os

        max_bytes = self._config.file_cache_max_mb * 1024 * 1024
        # (path, size, atime) — 每个文件只 stat 一次
        all_entries: list[tuple[Path, int, float]] = []

        def _collect(directory: Path) -> None:
            try:
                with os.scandir(directory) as it:
                    for entry in it:
                        if entry.is_file() and entry.name.endswith(".audio"):
                            st = entry.stat(follow_symlinks=False)
                            all_entries.append((Path(entry.path), st.st_size, st.st_atime))
            except OSError:
                pass

        _collect(self._file_dir)
        for user_dir in self._file_dir.iterdir():
            if user_dir.is_dir():
                _collect(user_dir)

        all_entries.sort(key=lambda e: e[2])  # sort by atime
        total = sum(e[1] for e in all_entries)
        while total > max_bytes and all_entries:
            path, size, _ = all_entries.pop(0)
            total -= size
            path.unlink(missing_ok=True)

    def clear(self) -> None:
        """清空所有缓存（包括所有用户子目录）"""
        self._memory.clear()
        for f in self._file_dir.glob("*.audio"):
            f.unlink(missing_ok=True)
        for user_dir in self._file_dir.iterdir():
            if user_dir.is_dir():
                for f in user_dir.glob("*.audio"):
                    f.unlink(missing_ok=True)


class TTSManager:
    """TTS 管理器

    对外暴露统一的语音合成接口，对内管理：
    - 引擎注册与选择
    - 人格语音映射
    - 双层音频缓存
    - 流式合成
    """

    def __init__(self, config: TTSConfig | None = None) -> None:
        self._config = config or TTSConfig()
        self._adapters: dict[str, TTSAdapter] = {}
        self._cache = TTSCache(self._config.cache)
        self._persona_voices: dict[str, dict[str, str]] = {}

    def register_adapter(self, adapter: TTSAdapter) -> None:
        """注册 TTS 适配器"""
        self._adapters[adapter.engine_id] = adapter
        logger.info("TTS 适配器已注册: %s", adapter.engine_id)

    def set_persona_voice(
        self,
        persona_id: str,
        engine: str,
        voice: str,
        rate: float = 1.0,
        pitch: float = 1.0,
    ) -> None:
        """为人格绑定语音配置"""
        self._persona_voices[persona_id] = {
            "engine": engine,
            "voice": voice,
            "rate": str(rate),
            "pitch": str(pitch),
        }

    def _resolve_engine(
        self,
        engine_id: str | None = None,
        persona_id: str | None = None,
    ) -> tuple[TTSAdapter, str, float, float]:
        """解析引擎、音色、语速、音调

        优先级：
        1. 显式指定的 engine_id
        2. 人格配置中的 engine/voice
        3. 全局默认配置
        4. 第一个可用引擎
        """
        target_engine = engine_id
        voice = self._config.default_voice
        rate, pitch = 1.0, 1.0

        # 人格配置
        if persona_id and persona_id in self._persona_voices:
            pv = self._persona_voices[persona_id]
            if not target_engine:
                target_engine = pv["engine"]
            voice = pv.get("voice", voice)
            rate = float(pv.get("rate", "1.0"))
            pitch = float(pv.get("pitch", "1.0"))

        # 全局默认
        if not target_engine:
            target_engine = self._config.default_engine

        # 查找适配器
        adapter = self._adapters.get(target_engine)
        if adapter is None:
            # 降级：找第一个可用的
            for aid, adp in self._adapters.items():
                adapter = adp
                target_engine = aid
                logger.warning("引擎 %s 不可用，降级到 %s", target_engine, aid)
                break

        if adapter is None:
            raise RuntimeError("没有可用的 TTS 引擎，请检查配置和依赖安装")

        return adapter, voice, rate, pitch

    async def synthesize(
        self,
        text: str,
        engine: str | None = None,
        voice: str | None = None,
        persona_id: str | None = None,
        rate: float | None = None,
        pitch: float | None = None,
        output_format: str = "mp3",
        use_cache: bool = True,
        user_id: str | None = None,
    ) -> bytes:
        """非流式合成，返回完整音频字节

        Args:
            text: 待合成文本
            engine: 指定引擎（可选）
            voice: 指定音色（可选）
            persona_id: 人设 ID（用于查找绑定的语音配置）
            rate: 语速倍率（可选）
            pitch: 音调倍率（可选）
            output_format: 输出格式
            use_cache: 是否使用缓存

        Returns:
            完整音频字节
        """
        if not self._config.enabled:
            raise RuntimeError("TTS 系统未启用")

        adapter, resolved_voice, resolved_rate, resolved_pitch = self._resolve_engine(
            engine, persona_id
        )
        final_voice = voice or resolved_voice
        final_rate = rate if rate is not None else resolved_rate
        final_pitch = pitch if pitch is not None else resolved_pitch

        # 查缓存
        if use_cache:
            cached = self._cache.get(adapter.engine_id, final_voice, text, user_id=user_id)
            if cached is not None:
                logger.debug(
                    "TTS 缓存命中: engine=%s voice=%s",
                    adapter.engine_id,
                    final_voice,
                )
                return cached

        # 合成
        audio = await adapter.synthesize(
            text,
            final_voice,
            final_rate,
            final_pitch,
            output_format,
        )

        # 写缓存
        if use_cache and audio:
            self._cache.put(adapter.engine_id, final_voice, text, audio, user_id=user_id)

        return audio

    async def synthesize_stream(
        self,
        text: str,
        engine: str | None = None,
        voice: str | None = None,
        persona_id: str | None = None,
        rate: float | None = None,
        pitch: float | None = None,
        output_format: str = "mp3",
    ):
        """流式合成，返回音频字节块异步迭代器

        流式结果不写入缓存，以避免状态管理复杂性。
        """
        if not self._config.enabled:
            raise RuntimeError("TTS 系统未启用")

        adapter, resolved_voice, resolved_rate, resolved_pitch = self._resolve_engine(
            engine, persona_id
        )
        final_voice = voice or resolved_voice
        final_rate = rate if rate is not None else resolved_rate
        final_pitch = pitch if pitch is not None else resolved_pitch

        async for chunk in adapter.synthesize_stream(
            text,
            final_voice,
            final_rate,
            final_pitch,
            output_format,
        ):
            yield chunk

    def list_engines(self) -> list[str]:
        """返回已注册的引擎 ID 列表"""
        return list(self._adapters.keys())

    def list_voices(self, engine: str | None = None) -> list[VoiceInfo]:
        """返回指定引擎（或所有引擎）的音色列表"""
        if engine:
            adapter = self._adapters.get(engine)
            if adapter:
                return adapter.list_voices()
            return []

        all_voices: list[VoiceInfo] = []
        for adapter in self._adapters.values():
            all_voices.extend(adapter.list_voices())
        return all_voices

    async def get_status(self) -> dict[str, Any]:
        """返回 TTS 系统状态"""
        import asyncio

        engine_ids = list(self._adapters.keys())
        results = await asyncio.gather(
            *(self._adapters[eid].is_available() for eid in engine_ids),
            return_exceptions=True,
        )
        engine_status: dict[str, bool] = {}
        for eid, result in zip(engine_ids, results, strict=False):
            engine_status[eid] = result if isinstance(result, bool) else False

        return {
            "enabled": self._config.enabled,
            "default_engine": self._config.default_engine,
            "default_voice": self._config.default_voice,
            "streaming": self._config.streaming,
            "registered_engines": self.list_engines(),
            "engine_available": engine_status,
            "persona_voices": dict(self._persona_voices),
            "cache_memory_entries": len(self._cache._memory),
        }

    def clear_cache(self) -> None:
        """清空音频缓存"""
        self._cache.clear()

    # ------------------------------------------------------------------
    # 流式缓冲区：收集 LLM 输出的文本 token，当检测到句末标点或超过
    # 阈值长度时触发合成，实现「边生成边播放」。
    # 设计参考: docs/tts-system.md 第9节
    # ------------------------------------------------------------------

    _SENTENCE_END_RE = re.compile(r"[。！？!?；;\n]")
    _SENTENCE_SPLIT_RE = re.compile(r"([。！？!?；;\n])")

    async def synthesize_streaming_buffered(
        self,
        text_stream: AsyncIterator[str],
        engine: str | None = None,
        voice: str | None = None,
        persona_id: str | None = None,
        rate: float | None = None,
        pitch: float | None = None,
        output_format: str = "mp3",
        buffer_threshold: int = 20,
        user_id: str | None = None,
    ) -> AsyncIterator[bytes]:
        """流式缓冲合成：收集 token，在句子边界处触发合成

        设计要求（tts-system.md 第9节）：
        - 收集 LLM 推送的文本 token
        - 检测到句末标点（。！？）、逗号或缓冲区超过阈值时触发合成
        - 产出音频块供前端按序播放

        Args:
            text_stream: 异步文本 token 迭代器
            engine/voice/persona_id/rate/pitch/output_format: 同 synthesize
            buffer_threshold: 缓冲区字符数阈值（默认 20）

        Yields:
            音频字节块
        """
        if not self._config.enabled:
            raise RuntimeError("TTS 系统未启用")

        adapter, resolved_voice, resolved_rate, resolved_pitch = self._resolve_engine(
            engine, persona_id
        )
        final_voice = voice or resolved_voice
        final_rate = rate if rate is not None else resolved_rate
        final_pitch = pitch if pitch is not None else resolved_pitch

        buffer_parts: list[str] = []
        buffer_len = 0

        async for token in text_stream:
            buffer_parts.append(token)
            buffer_len += len(token)

            # 在句末标点或超过阈值时触发合成
            should_flush = False
            if self._SENTENCE_END_RE.search(token):
                should_flush = True
            elif buffer_len >= buffer_threshold:
                # 超过阈值但没有标点，也在逗号处切分
                should_flush = True

            if should_flush and buffer_len > 0:
                buffer = "".join(buffer_parts)
                if not buffer.strip():
                    buffer_parts.clear()
                    buffer_len = 0
                else:
                    # 按句末标点切分，合成完整句子
                    parts = self._SENTENCE_SPLIT_RE.split(buffer)
                    complete_parts: list[str] = []
                    remainder = ""
                    for i, part in enumerate(parts):
                        if self._SENTENCE_END_RE.fullmatch(part):
                            complete_parts.append(part)
                        elif i < len(parts) - 1:
                            # 中间段且后面还有标点 → 包含在完整部分
                            complete_parts.append(part)
                        else:
                            remainder = part

                    complete = "".join(complete_parts)

                    if complete.strip():
                        # 查缓存
                        cached = self._cache.get(
                            adapter.engine_id,
                            final_voice,
                            complete,
                            user_id=user_id,
                        )
                        if cached is not None:
                            yield cached
                        else:
                            try:
                                audio = await adapter.synthesize(
                                    complete,
                                    final_voice,
                                    final_rate,
                                    final_pitch,
                                    output_format,
                                )
                                if audio:
                                    self._cache.put(
                                        adapter.engine_id,
                                        final_voice,
                                        complete,
                                        audio,
                                        user_id=user_id,
                                    )
                                    yield audio
                            except Exception as e:
                                logger.warning(
                                    "streaming_buffer_synthesize_failed",
                                    text_preview=complete[:50],
                                    error=str(e),
                                )
                    buffer_parts = [remainder] if remainder else []
                    buffer_len = len(remainder)

        # 处理剩余缓冲区
        if buffer_parts:
            final_text = "".join(buffer_parts).strip()
            if final_text:
                try:
                    audio = await adapter.synthesize(
                        final_text,
                        final_voice,
                        final_rate,
                        final_pitch,
                        output_format,
                    )
                    if audio:
                        yield audio
                except Exception as e:
                    logger.warning(
                        "streaming_buffer_final_synthesize_failed",
                        text_preview=final_text[:50],
                        error=str(e),
                    )

    # ------------------------------------------------------------------
    # 缓存预热：启动时预加载人格常用问候语到 L1 缓存
    # 设计参考: docs/tts-system.md 第10节
    # ------------------------------------------------------------------

    async def prewarm_cache(
        self,
        greeting_texts: list[str] | None = None,
        engine: str | None = None,
        voice: str | None = None,
        persona_id: str | None = None,
        user_id: str | None = None,
    ) -> int:
        """预热 TTS 缓存：预加载常用问候语到 L1 内存

        Args:
            greeting_texts: 要预热的文本列表。为 None 时使用默认问候语。
            engine: 指定引擎
            voice: 指定音色
            persona_id: 人设 ID

        Returns:
            成功预热的条目数
        """
        if not self._config.enabled:
            return 0

        default_greetings = [
            "你好呀～有什么我能帮你的吗？",
            "早上好！今天心情怎么样？",
            "晚上好～今天过得怎么样呀？",
            "好久不见！最近还好吗？",
            "嗯嗯，我在听呢，你继续说～",
        ]
        texts = greeting_texts or default_greetings

        warmed = 0
        for text in texts:
            try:
                await self.synthesize(
                    text,
                    engine=engine,
                    voice=voice,
                    persona_id=persona_id,
                    use_cache=True,
                    user_id=user_id,
                )
                warmed += 1
            except Exception as e:
                logger.debug("cache_prewarm_failed", text=text[:30], error=str(e))

        logger.info("TTS 缓存预热完成: %d/%d 条", warmed, len(texts))
        return warmed
