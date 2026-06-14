"""yuanbot_testkit — YuanBot 扩展测试工具包

提供 ``MockCore`` 和 ``TestAdapter`` 用于扩展的单元和集成测试。

用法::

    from yuanbot_testkit import MockCore, TestAdapter
"""

from yuanbot_testkit.fixtures import (
    configured_mock_core,
    mock_core,
    sample_bot_response_text,
    sample_config,
    sample_message_content,
    sample_messages,
    sample_user_message,
    test_adapter,
)
from yuanbot_testkit.mock_adapter import SentMessage, TestAdapter
from yuanbot_testkit.mock_core import CallRecord, MockCore

__all__ = [
    "MockCore",
    "TestAdapter",
    "CallRecord",
    "SentMessage",
    # 常用 fixtures（可直接在 conftest.py 中重导出）
    "mock_core",
    "test_adapter",
    "sample_messages",
    "sample_user_message",
    "sample_bot_response_text",
    "sample_config",
    "sample_message_content",
    "configured_mock_core",
]
