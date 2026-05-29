"""TTS 管理器 — 引擎选择、缓存、流式合成"""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
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

    def __init__(self, config: TTSCacheConfig) -> None:
        self._config = config
        self._memory: OrderedDict[str, bytes] = OrderedDict()
        self._file_dir = Path(config.file_cache_path)
        self._file_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _make_key(engine: str, voice: str, text: str) -> str:
        """生成缓存键: sha256(engine|voice|text[:200])"""
        content = f"{engine}|{voice}|{text[:200]}"
        return hashlib.sha256(content.encode()).hexdigest()

    def get(self, engine: str, voice: str, text: str) -> bytes | None:
        """查询缓存，优先 L1 内存"""
        key = self._make_key(engine, voice, text)

        # L1: 内存
        if key in self._memory:
            self._memory.move_to_end(key)
            return self._memory[key]

        # L2: 文件
        file_path = self._file_dir / f"{key}.audio"
        if file_path.exists():
            try:
                data = file_path.read_bytes()
                self._put_memory(key, data)
                return data
            except OSError:
                pass

        return None

    def put(self, engine: str, voice: str, text: str, audio: bytes) -> None:
        """写入缓存 (L1 + L2)"""
        key = self._make_key(engine, voice, text)

        # L1
        self._put_memory(key, audio)

        # L2
        try:
            file_path = self._file_dir / f"{key}.audio"
            file_path.write_bytes(audio)
            self._evict_file_cache()
        except OSError as e:
            logger.warning("TTS 文件缓存写入失败: %s", e)

    def _put_memory(self, key: str, data: bytes) -> None:
        """写入 L1 内存缓存"""
        if key in self._memory:
            self._memory.move_to_end(key)
        else:
            if len(self._memory) >= self._config.memory_size:
                self._memory.popitem(last=False)
            self._memory[key] = data

    def _evict_file_cache(self) -> None:
        """L2 文件缓存淘汰：按时间排序，超出容量上限时删除最旧文件"""
        max_bytes = self._config.file_cache_max_mb * 1024 * 1024
        files = sorted(self._file_dir.glob("*.audio"), key=lambda f: f.stat().st_atime)
        total = sum(f.stat().st_size for f in files)
        while total > max_bytes and files:
            oldest = files.pop(0)
            total -= oldest.stat().st_size
            oldest.unlink(missing_ok=True)

    def clear(self) -> None:
        """清空所有缓存"""
        self._memory.clear()
        for f in self._file_dir.glob("*.audio"):
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

        adapter, resolved_voice, resolved_rate, resolved_pitch = \
            self._resolve_engine(engine, persona_id)
        final_voice = voice or resolved_voice
        final_rate = rate if rate is not None else resolved_rate
        final_pitch = pitch if pitch is not None else resolved_pitch

        # 查缓存
        if use_cache:
            cached = self._cache.get(adapter.engine_id, final_voice, text)
            if cached is not None:
                logger.debug(
                    "TTS 缓存命中: engine=%s voice=%s",
                    adapter.engine_id, final_voice,
                )
                return cached

        # 合成
        audio = await adapter.synthesize(
            text, final_voice, final_rate, final_pitch, output_format,
        )

        # 写缓存
        if use_cache and audio:
            self._cache.put(adapter.engine_id, final_voice, text, audio)

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

        adapter, resolved_voice, resolved_rate, resolved_pitch = \
            self._resolve_engine(engine, persona_id)
        final_voice = voice or resolved_voice
        final_rate = rate if rate is not None else resolved_rate
        final_pitch = pitch if pitch is not None else resolved_pitch

        async for chunk in adapter.synthesize_stream(
            text, final_voice, final_rate, final_pitch, output_format,
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
        engine_status: dict[str, bool] = {}
        for eid, adapter in self._adapters.items():
            engine_status[eid] = await adapter.is_available()

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
