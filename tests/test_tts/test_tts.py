"""TTS 系统测试"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from yuanbot.tts.base import TTSAdapter, VoiceInfo
from yuanbot.tts.manager import TTSCache, TTSCacheConfig, TTSConfig, TTSManager

# ──────────────────────────────────────────────
# Mock 适配器
# ──────────────────────────────────────────────


class MockTTSAdapter(TTSAdapter):
    """用于测试的 Mock TTS 适配器"""

    def __init__(self, engine_id: str = "mock", available: bool = True) -> None:
        self._engine_id = engine_id
        self._available = available
        self.synthesize_calls: list[tuple] = []
        self.stream_calls: list[tuple] = []

    @property
    def engine_id(self) -> str:
        return self._engine_id

    async def synthesize(
        self, text: str, voice: str, rate: float = 1.0, pitch: float = 1.0, output_format: str = "mp3"
    ) -> bytes:
        self.synthesize_calls.append((text, voice, rate, pitch, output_format))
        # Use length to avoid non-ASCII in bytes literal
        return f"audio:{self._engine_id}:{voice}:{len(text)}".encode()

    async def synthesize_stream(
        self, text: str, voice: str, rate: float = 1.0, pitch: float = 1.0, output_format: str = "mp3"
    ) -> AsyncIterator[bytes]:
        self.stream_calls.append((text, voice, rate, pitch, output_format))
        for i in range(0, len(text), 10):
            yield f"chunk:{i}".encode()

    def list_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(f"{self._engine_id}-voice1", "Voice 1", "zh-CN", "female"),
            VoiceInfo(f"{self._engine_id}-voice2", "Voice 2", "zh-CN", "male"),
        ]

    async def is_available(self) -> bool:
        return self._available


# ──────────────────────────────────────────────
# TTSCache 测试
# ──────────────────────────────────────────────


class TestTTSCache:
    def test_make_key_deterministic(self) -> None:
        key1 = TTSCache._make_key("edge-tts", "voice1", "hello")
        key2 = TTSCache._make_key("edge-tts", "voice1", "hello")
        assert key1 == key2

    def test_make_key_different_inputs(self) -> None:
        key1 = TTSCache._make_key("edge-tts", "voice1", "hello")
        key2 = TTSCache._make_key("edge-tts", "voice1", "world")
        assert key1 != key2

    def test_memory_cache_hit(self, tmp_path) -> None:
        config = TTSCacheConfig(memory_size=10, file_cache_path=str(tmp_path / "cache"))
        cache = TTSCache(config)
        cache.put("edge-tts", "voice1", "hello", b"audio_data")
        result = cache.get("edge-tts", "voice1", "hello")
        assert result == b"audio_data"

    def test_memory_cache_miss(self, tmp_path) -> None:
        config = TTSCacheConfig(memory_size=10, file_cache_path=str(tmp_path / "cache"))
        cache = TTSCache(config)
        result = cache.get("edge-tts", "voice1", "nonexistent")
        assert result is None

    def test_file_cache_l2_hit(self, tmp_path) -> None:
        config = TTSCacheConfig(memory_size=2, file_cache_path=str(tmp_path / "cache"))
        cache = TTSCache(config)
        cache.put("edge-tts", "voice1", "hello", b"audio_data")

        cache._memory.clear()
        result = cache.get("edge-tts", "voice1", "hello")
        assert result == b"audio_data"

    def test_memory_lru_eviction(self, tmp_path) -> None:
        config = TTSCacheConfig(memory_size=2, file_cache_path=str(tmp_path / "cache"))
        cache = TTSCache(config)
        cache.put("e", "v", "text1", b"a1")
        cache.put("e", "v", "text2", b"a2")
        cache.put("e", "v", "text3", b"a3")

        assert len(cache._memory) == 2
        result = cache.get("e", "v", "text1")
        assert result == b"a1"

    def test_clear(self, tmp_path) -> None:
        config = TTSCacheConfig(memory_size=10, file_cache_path=str(tmp_path / "cache"))
        cache = TTSCache(config)
        cache.put("e", "v", "text1", b"a1")
        cache.clear()
        assert cache.get("e", "v", "text1") is None


# ──────────────────────────────────────────────
# TTSManager 测试
# ──────────────────────────────────────────────


class TestTTSManager:
    @pytest.fixture
    def manager(self, tmp_path) -> TTSManager:
        config = TTSConfig(
            default_engine="mock",
            default_voice="mock-voice1",
            cache=TTSCacheConfig(memory_size=10, file_cache_path=str(tmp_path / "cache")),
        )
        return TTSManager(config)

    @pytest.mark.asyncio
    async def test_register_adapter(self, manager: TTSManager) -> None:
        adapter = MockTTSAdapter("mock")
        manager.register_adapter(adapter)
        assert "mock" in manager.list_engines()

    @pytest.mark.asyncio
    async def test_synthesize_basic(self, manager: TTSManager) -> None:
        adapter = MockTTSAdapter("mock")
        manager.register_adapter(adapter)

        result = await manager.synthesize("hello", voice="mock-voice1")
        assert result == b"audio:mock:mock-voice1:5"
        assert len(adapter.synthesize_calls) == 1

    @pytest.mark.asyncio
    async def test_synthesize_cache_hit(self, manager: TTSManager) -> None:
        adapter = MockTTSAdapter("mock")
        manager.register_adapter(adapter)

        result1 = await manager.synthesize("hello", voice="mock-voice1")
        result2 = await manager.synthesize("hello", voice="mock-voice1")

        assert result1 == result2
        assert len(adapter.synthesize_calls) == 1

    @pytest.mark.asyncio
    async def test_synthesize_no_cache(self, manager: TTSManager) -> None:
        adapter = MockTTSAdapter("mock")
        manager.register_adapter(adapter)

        await manager.synthesize("hello", voice="mock-voice1", use_cache=False)
        await manager.synthesize("hello", voice="mock-voice1", use_cache=False)
        assert len(adapter.synthesize_calls) == 2

    @pytest.mark.asyncio
    async def test_synthesize_with_persona(self, manager: TTSManager) -> None:
        adapter = MockTTSAdapter("mock")
        manager.register_adapter(adapter)
        manager.set_persona_voice("persona1", "mock", "mock-voice2", rate=1.2, pitch=1.1)

        result = await manager.synthesize("hello", persona_id="persona1")
        assert result == b"audio:mock:mock-voice2:5"
        assert adapter.synthesize_calls[0][2] == 1.2
        assert adapter.synthesize_calls[0][3] == 1.1

    @pytest.mark.asyncio
    async def test_synthesize_engine_fallback(self, manager: TTSManager) -> None:
        adapter = MockTTSAdapter("fallback")
        manager.register_adapter(adapter)

        result = await manager.synthesize("hello", engine="nonexistent", voice="fallback-voice1")
        assert result == b"audio:fallback:fallback-voice1:5"

    @pytest.mark.asyncio
    async def test_synthesize_stream(self, manager: TTSManager) -> None:
        adapter = MockTTSAdapter("mock")
        manager.register_adapter(adapter)

        chunks = []
        async for chunk in manager.synthesize_stream("hello world", voice="mock-voice1"):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert len(adapter.stream_calls) == 1

    @pytest.mark.asyncio
    async def test_synthesize_disabled(self, manager: TTSManager) -> None:
        manager._config.enabled = False
        with pytest.raises(RuntimeError, match="TTS"):
            await manager.synthesize("hello")

    @pytest.mark.asyncio
    async def test_list_voices(self, manager: TTSManager) -> None:
        adapter = MockTTSAdapter("mock")
        manager.register_adapter(adapter)

        voices = manager.list_voices("mock")
        assert len(voices) == 2
        assert voices[0].id == "mock-voice1"

    @pytest.mark.asyncio
    async def test_list_voices_all(self, manager: TTSManager) -> None:
        adapter1 = MockTTSAdapter("engine1")
        adapter2 = MockTTSAdapter("engine2")
        manager.register_adapter(adapter1)
        manager.register_adapter(adapter2)

        voices = manager.list_voices()
        assert len(voices) == 4

    @pytest.mark.asyncio
    async def test_get_status(self, manager: TTSManager) -> None:
        adapter = MockTTSAdapter("mock")
        manager.register_adapter(adapter)

        status = await manager.get_status()
        assert status["enabled"] is True
        assert status["default_engine"] == "mock"
        assert "mock" in status["registered_engines"]
        assert status["engine_available"]["mock"] is True

    @pytest.mark.asyncio
    async def test_clear_cache(self, manager: TTSManager) -> None:
        adapter = MockTTSAdapter("mock")
        manager.register_adapter(adapter)

        await manager.synthesize("hello", voice="mock-voice1")
        manager.clear_cache()

        await manager.synthesize("hello", voice="mock-voice1")
        assert len(adapter.synthesize_calls) == 2

    @pytest.mark.asyncio
    async def test_no_adapter_raises(self, manager: TTSManager) -> None:
        with pytest.raises(RuntimeError, match="TTS"):
            await manager.synthesize("hello")


# ──────────────────────────────────────────────
# VoiceInfo 测试
# ──────────────────────────────────────────────


class TestVoiceInfo:
    def test_to_dict(self) -> None:
        voice = VoiceInfo("id1", "Voice 1", "zh-CN", "female")
        d = voice.to_dict()
        assert d["id"] == "id1"
        assert d["name"] == "Voice 1"
        assert d["language"] == "zh-CN"
        assert d["gender"] == "female"


# ──────────────────────────────────────────────
# TTSAdapter 默认方法测试
# ──────────────────────────────────────────────


class TestTTSAdapterDefaults:
    def test_get_default_voice(self) -> None:
        adapter = MockTTSAdapter("mock")
        assert adapter.get_default_voice() == "mock-voice1"
