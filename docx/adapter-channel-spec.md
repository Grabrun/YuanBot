# 消息通道适配器规范 v1.0

## 1. 概述

消息通道适配器将不同即时通讯平台的消息统一标准化为 `UserMessage` / `BotResponse`，
屏蔽平台差异，确保编排层与具体平台解耦。

## 2. 标准化接口

```python
class ChannelAdapter(ABC):
    async def initialize(config: ChannelConfig) -> None
    async def listen(callback: Callable[[UserMessage], Awaitable[BotResponse]]) -> None
    async def send_message(target_id: str, content: MessageContent) -> SendResult
    def get_platform_user_id(raw_event: Any) -> str

    @property
    def platform_name(self) -> str
    @property
    def supported_content_types(self) -> list[ContentType]
```

## 3. 通道文件结构

```
adapters/channel/
├── base.py              # 基类（用户ID映射、会话管理）
├── telegram_adapter.py  # Telegram 适配器
├── web_adapter.py       # Web (WebSocket) 适配器
└── __init__.py          # 统一导出
```

## 4. Web 通道适配器设计

### 4.1 通信协议

- **WebSocket**：实时双向通信，用于在线聊天
- **REST API**：可选的 HTTP 接口，用于单次请求/响应

### 4.2 连接流程

```
客户端                     YuanBot Server
  │                             │
  │─── WS Connect ────────────→│
  │←── WS Connected (session_id)│
  │                             │
  │─── WS Message (text) ─────→│
  │←── WS Message (response) ──│
  │                             │
  │─── WS Close ──────────────→│
```

### 4.3 消息格式

```json
// 客户端 → 服务端
{
  "type": "message",
  "content_type": "text",
  "text": "你好",
  "user_id": "web_user_123",
  "metadata": {}
}

// 服务端 → 客户端
{
  "type": "response",
  "content_type": "text",
  "text": "你好呀~",
  "message_id": "msg_xxx",
  "metadata": {}
}

// 心跳
{"type": "ping"}
{"type": "pong"}
```

### 4.4 会话管理

- 每个 WebSocket 连接绑定一个 session_id
- 连接断开后，session 保留一定时间（默认 5 分钟）
- 重连时可通过 session_id 恢复上下文
