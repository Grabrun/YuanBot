"""YuanBot 测试配置"""

import pytest

from yuanbot.config import YuanBotConfig
from yuanbot.memory.manager import MemoryManager
from yuanbot.persona.default import DefaultPersona


@pytest.fixture
def config():
    """默认测试配置"""
    return YuanBotConfig()


@pytest.fixture
def memory_manager(config):
    """记忆管理器（纯内存模式）"""
    return MemoryManager(config=config.memory.model_dump())


@pytest.fixture
def persona():
    """默认人设"""
    return DefaultPersona()
