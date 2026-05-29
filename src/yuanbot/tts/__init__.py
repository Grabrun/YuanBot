"""YuanBot 语音合成系统 (TTS)"""

from yuanbot.tts.base import TTSAdapter
from yuanbot.tts.manager import TTSCacheConfig, TTSConfig, TTSManager

__all__ = ["TTSAdapter", "TTSManager", "TTSConfig", "TTSCacheConfig"]
