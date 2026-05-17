🌸 缘·Bot 接入与通信系统详细设计文档 (v1.4)

版本历史

版本 日期 修改内容
v1.0 2026-05-17 初始详细设计，基于项目总体架构 v1.4

---

1. 系统定位与目标

接入与通信系统是 缘·Bot 的“五官与声带”，负责与外部即时通讯平台建立双向连接。其核心目标为：

· 平台无关性：将 Telegram、Discord、企业微信、Web Chat 等异构平台的通信协议抽象为统一的内部消息格式，使核心业务逻辑完全与平台解耦。
· 会话连续性：在用户跨平台切换时，通过统一的身份链接机制，保证记忆和对话上下文的连续性。
· 高可用与可扩展：通过事件驱动架构和标准化适配器接口，支持热插拔式增减消息通道，并承载高并发消息吞吐。
· 安全可控：实施严格的认证鉴权、数据加密和隐私保护策略。

---

2. 系统架构概览

```
┌────────────────────────────────────────────────────────────┐
│                    外部消息平台                              │
│  Telegram | Discord | WeCom | WebSocket (Web Chat) | ...    │
└──────────┬──────────────────────────────────────┬───────────┘
           │  Webhook / WebSocket / Long Polling  │
           ↓                                      ↓
┌────────────────────────────────────────────────────────────┐
│                    接入与通信系统                            │
├────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  │
│  │                 统一网关 (YuanGateway)                │  │
│  │  · 请求路由  · 会话绑定  · 认证鉴权  · 心跳/健康检查  │  │
│  └───────────┬──────────────────────────┬───────────────┘  │
│              │                          │                  │
│  ┌───────────▼──────────┐  ┌────────────▼──────────────┐  │
│  │   消息通道适配器管理器  │  │   主动推送调度器           │  │
│  │   Adapter Manager     │  │   Push Dispatcher         │  │
│  └───────────┬──────────┘  └────────────┬──────────────┘  │
│              │                          │                  │
│  ┌───────────▼──────────────────────────▼──────────────┐  │
│  │                事件队列 (Event Queue)                 │  │
│  │         Redis Streams / RabbitMQ / NATS             │  │
│  └───────────────────────┬────────────────────────────┘  │
│                          │                                │
│  ┌───────────────────────▼────────────────────────────┐  │
│  │              消息标准化与路由模块                    │  │
│  │   · UserMessage 构建  · 平台 ID 解析  · 上下文关联  │  │
│  └───────────────────────┬────────────────────────────┘  │
│                          │                                │
└──────────────────────────┼────────────────────────────────┘
                           ↓
              核心编排层 (Orchestrator)
```

· 统一网关：对外暴露统一的 HTTP/WebSocket 接口，对内管理所有通道适配器的生命周期。
· 消息通道适配器：平台特有的协议实现，负责接收消息并转化为标准格式，以及将响应发送回平台。
· 事件队列：解耦网关与编排层，实现异步处理，保障高吞吐量，同时支持离线主动推送。
· 消息标准化模块：完成最终的消息合法性校验、用户身份关联、会话绑定。

---

3. 统一网关设计

3.1 职责

· 入口收敛：所有外部平台的消息均通过网关定义的统一端点（如 /gateway/inbound/{channel}）进入，屏蔽平台细节。
· TLS 终止：提供 HTTPS 支持，确保外部通信加密。
· 认证鉴权：对每个平台进行独立的身份验证（如 Telegram Bot Token、Discord Public Key 验证）。
· 会话绑定：根据平台用户 ID 和平台名称，将请求绑定到内部全局唯一的 yuanbot_user_id 和 session_id。
· 健康检查：提供 /healthz 端点，上报各通道适配器连通性。

3.2 路由规则

路径 方法 说明
/gateway/inbound/{channel} POST 接收来自特定通道的 Webhook 消息。{channel} 为通道标识，如 telegram、discord。
/gateway/ws/chat GET 内置 Web Chat 的 WebSocket 升级端点。
/gateway/healthz GET 网关及各通道适配器健康状态。

3.3 请求处理流程

1. 网关收到请求，根据 URL 中的 channel 或 WebSocket 握手标识选择对应的适配器。
2. 调用适配器的 verify_request(request) 进行平台级认证（如 Telegram 的 secret token、Discord 的签名验证）。
3. 认证通过后，调用适配器的 parse_message(request) 生成平台原始事件对象。
4. 调用适配器的 get_platform_user_id(raw_event) 提取平台用户 ID。
5. 通过 身份链接服务 将 (platform, platform_user_id) 映射为内部的 yuanbot_user_id，并创建或恢复 session_id。
6. 调用适配器的 normalize_message(raw_event, yuanbot_user_id, session_id) 生成标准 UserMessage。
7. 将 UserMessage 发布到事件队列的 inbound 主题，异步等待编排层处理。
8. 立即返回 HTTP 200 给平台（对于需要快速响应的 Webhook）。

3.4 身份链接服务

· 维护一个 identity 表（SQLite/MySQL）：
  ```
  platform | platform_user_id | yuanbot_user_id
  ```
· 首次交互时自动创建映射，生成一个全局唯一的 yuanbot_user_id。
· 支持用户手动关联多个平台账号（如绑定 Telegram 和 Discord 为同一用户），通过 yuanbot_user_id 合并。

---

4. 消息通道适配器设计

4.1 标准化接口定义

所有通道适配器必须实现 ChannelAdapter 抽象基类（Python 伪代码）：

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Any, Optional, List, AsyncIterator
from enum import Enum

class ContentType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    VIDEO = "video"
    FILE = "file"

@dataclass
class UserMessage:
    platform: str
    platform_user_id: str
    yuanbot_user_id: str
    session_id: str
    content_type: ContentType
    text: Optional[str] = None
    media_url: Optional[str] = None
    media_bytes: Optional[bytes] = None  # 适用于小文件直接传递
    timestamp: float = 0.0
    metadata: dict = None
    reply_to_message_id: Optional[str] = None  # 被回复的消息ID

@dataclass
class BotResponse:
    content: "MessageContent"
    suggested_tools: Optional[List["ToolInvocation"]] = None
    proactive_followups: Optional[List["ProactiveTask"]] = None

class ChannelAdapter(ABC):
    @abstractmethod
    def initialize(self, config: dict) -> None:
        """初始化适配器，建立连接，注册Webhook等"""
        pass

    @abstractmethod
    def verify_request(self, request: Any) -> bool:
        """验证请求合法性（如签名、Token）"""
        pass

    @abstractmethod
    def parse_message(self, request: Any) -> Any:
        """将原始请求解析为平台事件对象"""
        pass

    @abstractmethod
    def get_platform_user_id(self, event: Any) -> str:
        """从事件中提取平台用户ID"""
        pass

    @abstractmethod
    def normalize_message(
        self, event: Any, yuanbot_user_id: str, session_id: str
    ) -> UserMessage:
        """将平台事件转化为标准 UserMessage"""
        pass

    @abstractmethod
    async def send_message(self, target_id: str, response: BotResponse) -> bool:
        """向指定平台用户发送消息，返回是否成功"""
        pass

    @abstractmethod
    def get_platform_name(self) -> str:
        """返回平台标识，如 'telegram'"""
        pass

    @abstractmethod
    def get_supported_content_types(self) -> List[ContentType]:
        """返回该平台支持的内容类型"""
        pass
```

4.2 适配器生命周期

1. 加载：系统启动时扫描 configs/Channels/ 目录下所有 .yaml 文件，根据 adapter 字段动态加载对应适配器类。
2. 初始化：调用 initialize(config['config'])，完成 Webhook 注册、长连接建立等。
3. 运行：持续接收消息，通过网关处理。
4. 关闭：系统退出时调用 shutdown() 取消 Webhook 或关闭连接。

4.3 配置规范

详见 6. 配置管理。

---

5. 消息标准化详细定义

5.1 消息类型与内容

· TEXT：纯文本或 Markdown 消息，text 字段必填。
· IMAGE：图片消息，media_url 为图片临时链接，同时可选 media_bytes。
· VOICE：语音消息，提供 media_url。
· VIDEO：视频消息。
· FILE：文件消息，附带 file_name 等元数据（可存储在 metadata 中）。

5.2 回复与引用

UserMessage 中的 reply_to_message_id 字段用于实现对话线程。BotResponse 中应包含引用原始消息 ID 的能力，以支持回复形式发送。

5.3 平台特有元数据

metadata 是一个字典，用于存放平台特有的字段（如 Telegram 的 chat_id、Discord 的 guild_id），使适配器在发送响应时能正确路由。

---

6. 配置管理

6.1 目录结构

```
configs/
└── Channels/
    ├── telegram.yaml
    ├── discord.yaml
    ├── wecom.yaml
    └── webchat.yaml
```

6.2 配置文件模板

示例：telegram.yaml

```yaml
adapter: telegram-channel-adapter
enabled: true
config:
  bot_token: "YOUR_BOT_TOKEN"
  webhook:
    enabled: true
    url: "https://yourdomain.com/gateway/inbound/telegram"
    secret_token: "a-secret-string"
  polling:  # 若 webhook 不可用，可使用长轮询
    enabled: false
    interval: 2.0
```

示例：discord.yaml

```yaml
adapter: discord-channel-adapter
enabled: true
config:
  bot_token: "YOUR_BOT_TOKEN"
  public_key: "DISCORD_PUBLIC_KEY"  # 用于签名验证
  intents: ["GUILD_MESSAGES", "MESSAGE_CONTENT"]
```

示例：webchat.yaml

```yaml
adapter: webchat-channel-adapter
enabled: true
config:
  ws_path: "/gateway/ws/chat"
  allowed_origins: ["*"]
  auth_required: false  # 内置Web聊天可无认证
```

6.3 动态热加载

网关可监听配置文件变化，当新的 enabled: true 的通道被添加或配置修改后，自动加载或重载适配器，无需重启整个系统。

---

7. 事件队列与异步通信

7.1 队列选型

· 开发环境：Redis Streams（默认，与工作记忆缓存共用 Redis）。
· 生产环境：可切换至 RabbitMQ 或 NATS，以支持持久化和更高可靠性。

7.2 消息主题设计

主题 方向 说明
yuanbot.inbound 网关 → 编排层 标准化后的用户消息
yuanbot.outbound.{channel} 编排层 → 网关 需发送给用户的响应，按通道划分
yuanbot.proactive.push 编排层/主动系统 → 网关 主动推送任务，包含通道及目标用户信息

7.3 主动推送流程

1. 编排层或主动陪伴系统向 yuanbot.proactive.push 发布消息，格式如：
   ```json
   {
     "channel": "telegram",
     "target_id": "telegram_user_123",
     "response": { ... }
   }
   ```
2. 网关中的主动推送调度器消费该主题，找到对应适配器，调用 send_message。

---

8. 安全设计

8.1 认证鉴权

· Telegram：通过 X-Telegram-Bot-Api-Secret-Token 头验证 Webhook 来源。
· Discord：使用 Ed25519 公钥验证 HTTP 签名。
· 企业微信：验证消息签名（SHA1）。
· Web Chat：可选 JWT 认证；本地部署可默认信任。

8.2 通信加密

· 所有外部 Webhook 端点强制 HTTPS（TLS 1.2+）。
· WebSocket 连接使用 wss://。

8.3 防滥用与限流

· 每个通道适配器可配置最大每秒接收消息数（rate limit），超过则返回 429。
· 对同一平台用户的消息频率进行监控，防止刷屏攻击。

---

9. 预集成通道的具体实现说明

9.1 Telegram 适配器

· API 方式：使用 python-telegram-bot 或 aiogram 库。
· 消息解析：支持文本、图片、语音、视频、文件。将 Message 对象转化为 UserMessage。
· 发送接口：调用 Bot API sendMessage、sendPhoto 等。支持回复（reply_to_message_id）。
· 媒体处理：媒体文件先下载到临时存储，生成内部 URL 或直接以字节流传递。

9.2 Discord 适配器

· API 方式：使用 discord.py 或 nextcord。
· 网关连接：通过 WebSocket 连接到 Discord Gateway，维护心跳。
· 消息解析：监听 on_message 事件，生成 UserMessage。reply_to_message_id 对应 Discord 的 message_reference。
· 发送接口：支持 channel.send() 及 Embed 等丰富格式。

9.3 企业微信适配器

· API 方式：企业微信机器人回调。
· 消息解析：支持文本、图片、语音等多种类型。
· 加密通信：需要使用企业微信提供的加解密库解析回调消息。

9.4 Web Chat 适配器

· API 方式：基于 FastAPI WebSocket 端点。
· 协议：简单的 JSON 帧，格式与 UserMessage 和 BotResponse 直接映射。
· 优点：零网络配置，适合本地测试和自托管 Web 界面。

---

10. 扩展开发指南

开发者若要贡献新的消息通道适配器（如 WhatsApp、Line），需遵循以下步骤：

1. 创建扩展仓库：目录结构如下：
   ```
   yuanbot-channel-whatsapp/
   ├── manifest.json
   ├── adapter.py
   ├── requirements.txt
   └── README.md
   ```
2. 实现 ChannelAdapter 接口：继承自 yuanbot_core.channel_adapter.ChannelAdapter，重写所有抽象方法。
3. 编写 manifest.json：
   ```json
   {
     "name": "whatsapp-channel-adapter",
     "version": "1.0.0",
     "platform": "whatsapp",
     "author": "contributor",
     "config_schema": { ... }
   }
   ```
4. 在 configs/Channels/ 中添加配置：如 whatsapp.yaml。
5. 测试与提交：通过 CI 验证接口合规性后提交到社区市场。

---

11. 性能与可靠性

· 并发处理：网关采用异步框架（FastAPI + asyncio），每个适配器也基于异步 IO，可轻松处理数千 QPS。
· 消息持久化：事件队列支持持久化，防止系统崩溃时消息丢失。
· 通道重连机制：对于 WebSocket 类适配器，实现自动重连与指数退避。
· 监控：网关暴露 Prometheus 指标，包括消息接收量、处理延迟、错误率等。

---

本详细设计为接入与通信系统的最终实现提供了完整蓝图，确保缘·Bot 能够与各大平台稳定、安全、高效地对话。