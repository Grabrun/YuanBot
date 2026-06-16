# API 参考

YuanBot 提供完整的 RESTful API 和 WebSocket 接口。

**基础 URL**: `http://localhost:8000`

## 认证方式

YuanBot 采用 JWT (JSON Web Token) 认证机制。

1. 通过 `/api/auth/login` 或 `/api/auth/api-key` 获取 Token
2. 后续请求通过 `Authorization: Bearer <token>` 或 Cookie 携带

## API 概览

| 分类 | 路由前缀 | 说明 |
|------|----------|------|
| 认证 | `/api/auth` | 登录、登出、Token 刷新 |
| 会话 | `/api/conversations` | 会话管理与消息历史 |
| 聊天 | `/api/chat` | 发送消息并获取 AI 回复 |
| 管理 | `/api/admin` | 用户管理、备份、监控 |
| 人格 | `/api/persona` | 人设切换与管理 |
| Provider | `/api/providers` | AI 提供商管理 |
| 记忆 | `/api/memory` | 记忆数据查询 |
| 主动陪伴 | `/api/proactive` | 主动任务管理 |
| TTS | `/api/tts` | 语音合成 |
| 市场 | `/api/marketplace` | 扩展市场 |
| GDPR | `/api/gdpr` | 数据导出与删除 |

## 聊天 API

### POST /api/chat

发送消息并获取 AI 回复。

**请求体**：

```json
{
  "content": "你好，今天天气怎么样？",
  "conversation_id": "conv-uuid-1234"
}
```

**响应**：

```json
{
  "conversation_id": "conv-uuid-1234",
  "user_message": {
    "message_id": "msg-uuid-010",
    "content": "你好，今天天气怎么样？"
  },
  "ai_message": {
    "message_id": "msg-uuid-011",
    "content": "你好呀~ 我没有实时天气数据，不过你可以告诉我你在哪个城市，我帮你查一下哦！"
  }
}
```

## WebSocket 端点

### /ws/chat

认证聊天 WebSocket，支持流式响应。

**连接方式**：`ws://localhost:8000/ws/chat?token=<jwt>`

**客户端 → 服务端**：

```json
{"type": "message", "text": "你好", "conversation_id": "conv-uuid-1234"}
```

**服务端 → 客户端**：

```json
{"type": "stream_start", "conversation_id": "conv-uuid-1234"}
{"type": "stream_delta", "delta": "你好呀~"}
{"type": "stream_end", "conversation_id": "conv-uuid-1234", "full_text": "你好呀~ 今天过得怎么样？"}
```

## 健康检查

```bash
GET /healthz    # 存活探针
GET /readyz     # 就绪探针
```

## 通道适配器 API

YuanBot 的通道适配器 API 文档基于开源实现整理，供开发参考：

| 通道 | 协议 | 文档 |
|------|------|------|
| **NapCat QQ** | OneBot v11 (HTTP API + 事件上报) | [NapCat API 文档](https://napcat.apifox.cn) |
| **微信 iLink Bot** | 腾讯 iLink Bot API (长轮询 + CDN 加密传输) | 基于 `@tencent-weixin/openclaw-weixin` 源码整理 |

::: tip
通道适配器源码位于 `src/yuanbot/adapters/channel/`，完整 API 参考见 `docs/channels-apis/` 目录。
:::

完整 API 文档请参考 [GitHub 源码](https://github.com/Grabrun/YuanBot)。
