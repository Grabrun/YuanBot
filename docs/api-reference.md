---
title: API 参考手册
description: YuanBot RESTful API 和 WebSocket 接口完整文档
---

# API 参考手册

YuanBot 提供完整的 RESTful API 和 WebSocket 接口，涵盖认证、会话管理、系统管理、人格控制、AI Provider 管理、记忆系统、主动陪伴、语音合成、扩展市场、GDPR 合规等功能。

**基础 URL**: `http://localhost:8000`

---

## 目录

- [认证方式](#认证方式)
- [1. 认证 API](#1-认证-api)
- [2. 会话管理 API](#2-会话管理-api)
- [3. 管理 API](#3-管理-api)
- [4. 人格 API](#4-人格-api)
- [5. Provider API](#5-provider-api)
- [6. 记忆 API](#6-记忆-api)
- [7. 主动陪伴 API](#7-主动陪伴-api)
- [8. TTS 语音合成 API](#8-tts-语音合成-api)
- [9. 扩展与市场 API](#9-扩展与市场-api)
- [10. GDPR API](#10-gdpr-api)
- [11. 健康检查与监控](#11-健康检查与监控)
- [12. WebSocket 端点](#12-websocket-端点)

---

## 认证方式

YuanBot 采用 JWT (JSON Web Token) 认证机制。认证流程如下：

1. 通过 `/api/auth/login` 或 `/api/auth/api-key` 获取 JWT Token
2. 后续请求通过以下方式携带 Token（任选其一）：
   - **Cookie**: 自动设置 `yuanbot_token` HttpOnly Cookie
   - **Authorization Header**: `Authorization: Bearer <token>`
3. Token 默认有效期 24 小时，可通过 `/api/auth/refresh` 续期

**未认证响应** (401):

```json
{
  "detail": "Not authenticated"
}
```

**权限不足响应** (403):

```json
{
  "detail": "Admin access required"
}
```

---

## 1. 认证 API

**路由前缀**: `/api/auth`
**源文件**: `auth/routes.py`

### POST /api/auth/login

用户名密码登录，验证成功后返回 JWT Token 并设置 Cookie。

**认证要求**: 无需认证

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | ✅ | 用户名 |
| `password` | string | ✅ | 密码 |

```json
{
  "username": "admin",
  "password": "your_password"
}
```

**响应** (200):

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "user_id": "a1b2c3d4-...",
    "username": "admin",
    "display_name": "管理员",
    "role": "admin",
    "enabled": true,
    "created_at": "2025-01-01T00:00:00",
    "last_login": "2025-06-10T09:00:00",
    "has_api_key": false
  },
  "expires_in": 86400
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 401 | 用户名或密码错误 |

---

### POST /api/auth/api-key

使用长期 API Key 换取短期 Session Token。

**认证要求**: 无需认证

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `api_key` | string | ✅ | API Key |

```json
{
  "api_key": "yb_xxxxxxxxxxxxxxxx"
}
```

**响应** (200): 同 `/api/auth/login`

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 401 | 无效的 API Key 或用户已禁用 |

---

### POST /api/auth/logout

注销当前会话，清除 Cookie。

**认证要求**: 需要登录

**响应** (200):

```json
{
  "status": "ok"
}
```

---

### POST /api/auth/refresh

刷新即将过期的 Token，验证当前 Token 有效后签发新 Token。

**认证要求**: 需要登录

**响应** (200):

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 86400
}
```

---

### GET /api/auth/me

获取当前登录用户的详细信息。

**认证要求**: 需要登录

**响应** (200):

```json
{
  "user_id": "a1b2c3d4-...",
  "username": "admin",
  "display_name": "管理员",
  "role": "admin",
  "enabled": true,
  "created_at": "2025-01-01T00:00:00",
  "last_login": "2025-06-10T09:00:00",
  "has_api_key": false
}
```

---

### POST /api/auth/setup

首次管理员设置。当系统中没有管理员用户时，允许创建第一个管理员账号。已有管理员存在时返回 409。

**认证要求**: 无需认证

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | ✅ | 用户名（3-32 字符） |
| `password` | string | ✅ | 密码（6-128 字符） |
| `display_name` | string | ❌ | 显示名称，默认同用户名 |

```json
{
  "username": "admin",
  "password": "secure_password",
  "display_name": "管理员"
}
```

**响应** (200): 同 `/api/auth/login`

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 409 | 管理员已存在，请使用登录接口 |

---

### GET /api/auth/setup/status

检查系统是否需要首次设置。

**认证要求**: 无需认证

**响应** (200):

```json
{
  "needs_setup": false,
  "user_count": 3
}
```

---

## 2. 会话管理 API

**源文件**: `auth/conversation_routes.py`

### GET /api/conversations

获取当前用户的会话列表。

**认证要求**: 需要登录

**响应** (200):

```json
{
  "conversations": [
    {
      "conversation_id": "conv-uuid-1234",
      "title": "新会话",
      "created_at": "2025-06-10T08:00:00",
      "updated_at": "2025-06-10T09:30:00",
      "message_count": 12
    }
  ]
}
```

---

### POST /api/conversations

新建会话。

**认证要求**: 需要登录

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | ❌ | 会话标题，默认 `"新会话"` |

```json
{
  "title": "关于天气的对话"
}
```

**响应** (200):

```json
{
  "conversation_id": "conv-uuid-5678",
  "title": "关于天气的对话",
  "created_at": "2025-06-10T09:50:00"
}
```

---

### GET /api/conversations/{id}

获取会话详情（自动校验归属权）。

**认证要求**: 需要登录

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 会话 ID |

**响应** (200):

```json
{
  "conversation_id": "conv-uuid-1234",
  "title": "新会话",
  "created_at": "2025-06-10T08:00:00",
  "updated_at": "2025-06-10T09:30:00",
  "message_count": 12
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | 会话不存在或不属于当前用户 |

---

### DELETE /api/conversations/{id}

删除会话（自动校验归属权）。

**认证要求**: 需要登录

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 会话 ID |

**响应** (200):

```json
{
  "status": "ok"
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | 会话不存在 |

---

### GET /api/conversations/{id}/messages

获取会话历史消息，支持分页。

**认证要求**: 需要登录

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 会话 ID |

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | 50 | 每页数量（1-200） |
| `offset` | int | 0 | 偏移量 |

**响应** (200):

```json
{
  "messages": [
    {
      "message_id": "msg-uuid-001",
      "role": "user",
      "content": "你好",
      "timestamp": "2025-06-10T08:00:01"
    },
    {
      "message_id": "msg-uuid-002",
      "role": "assistant",
      "content": "你好呀~ 今天过得怎么样？",
      "timestamp": "2025-06-10T08:00:03"
    }
  ],
  "total": 12
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | 会话不存在 |

---

### GET /api/messages/search

跨会话全文搜索消息。优先使用 SQLite FTS5 全文搜索引擎，不可用时自动回退到 JSON 存储搜索。

**认证要求**: 需要登录

**查询参数**:

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `q` | string | ✅ | — | 搜索关键词（最少 1 字符） |
| `limit` | int | ❌ | 50 | 返回数量（1-200） |
| `offset` | int | ❌ | 0 | 偏移量 |

**响应** (200):

```json
{
  "query": "天气",
  "results": [
    {
      "message_id": "msg-uuid-005",
      "conversation_id": "conv-uuid-1234",
      "role": "user",
      "content": "今天天气怎么样？",
      "timestamp": "2025-06-10T08:10:00"
    }
  ],
  "count": 1,
  "engine": "fts5"
}
```

---

### GET /api/conversations/{id}/export

导出会话数据，支持 Markdown 和 JSON 两种格式。

**认证要求**: 需要登录

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 会话 ID |

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `format` | string | `markdown` | 导出格式：`markdown` 或 `json` |

**响应**:

- `format=markdown`: 返回 `text/markdown` 文件，`Content-Disposition` 为 `attachment`
- `format=json`: 返回 JSON 文件，`Content-Disposition` 为 `attachment`

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | 会话不存在 |

---

### POST /api/chat

发送消息并获取 AI 回复（同步模式）。

**认证要求**: 需要登录

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `content` | string | ✅ | 消息内容 |
| `conversation_id` | string | ❌ | 会话 ID，不指定则新建会话 |

```json
{
  "content": "你好，今天天气怎么样？",
  "conversation_id": "conv-uuid-1234"
}
```

**响应** (200):

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

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | 指定的会话不存在 |

---

## 3. 管理 API

**路由前缀**: `/api/admin`
**源文件**: `auth/admin_routes.py`
**认证要求**: 所有管理接口均需要 **管理员** 权限

### GET /api/admin/users

列出所有用户。

**响应** (200):

```json
{
  "users": [
    {
      "user_id": "a1b2c3d4-...",
      "username": "admin",
      "display_name": "管理员",
      "role": "admin",
      "enabled": true,
      "created_at": "2025-01-01T00:00:00",
      "last_login": "2025-06-10T09:00:00",
      "has_api_key": true
    }
  ],
  "total": 3
}
```

---

### POST /api/admin/users

创建新用户。

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | ✅ | 用户名 |
| `password` | string | ✅ | 密码 |
| `display_name` | string | ❌ | 显示名称 |
| `role` | string | ❌ | 角色：`admin` 或 `user`，默认 `user` |

```json
{
  "username": "alice",
  "password": "secure_pass",
  "display_name": "Alice",
  "role": "user"
}
```

**响应** (200):

```json
{
  "user": {
    "user_id": "e5f6g7h8-...",
    "username": "alice",
    "display_name": "Alice",
    "role": "user",
    "enabled": true,
    "created_at": "2025-06-10T09:55:00",
    "last_login": null,
    "has_api_key": false
  }
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 409 | 用户名已存在 |

---

### DELETE /api/admin/users/{id}

删除用户。

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 用户 ID |

**响应** (200):

```json
{
  "status": "ok"
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 400 | 不能删除自己 |
| 404 | 用户不存在 |

---

### POST /api/admin/users/{id}/api-key

为用户生成 API Key。

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 用户 ID |

**响应** (200):

```json
{
  "api_key": "yb_a1b2c3d4e5f6g7h8i9j0...",
  "user_id": "e5f6g7h8-..."
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | 用户不存在 |

---

### DELETE /api/admin/users/{id}/api-key

吊销用户的 API Key。

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 用户 ID |

**响应** (200):

```json
{
  "status": "ok"
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | 用户不存在或无 API Key |

---

### GET /api/admin/metrics

获取系统运行指标，包括 CPU、内存、磁盘使用率和 YuanBot 业务数据。

**响应** (200):

```json
{
  "system": {
    "python_version": "3.12.0 (main, ...)",
    "platform": "linux",
    "cpu_percent": 12.5,
    "memory": {
      "total_gb": 16.0,
      "used_percent": 45.2
    },
    "disk": {
      "total_gb": 100.0,
      "used_percent": 32.1
    }
  },
  "yuanbot": {
    "users": {
      "total": 3,
      "admin": 1
    },
    "conversations": {
      "total": 25,
      "messages": 312
    }
  }
}
```

---

### POST /api/admin/backup

触发系统备份，创建 tar.gz 归档文件。

**响应** (200):

```json
{
  "status": "ok",
  "name": "backup_20250610_095500.tar.gz",
  "path": "data/backups/backup_20250610_095500.tar.gz",
  "size_bytes": 1048576
}
```

---

### GET /api/admin/backups

列出所有备份文件。

**响应** (200):

```json
{
  "backups": [
    {
      "name": "backup_20250610_095500.tar.gz",
      "size_bytes": 1048576,
      "created_at": "2025-06-10T09:55:00"
    }
  ],
  "total": 1
}
```

---

### POST /api/admin/restore

从备份恢复系统数据。

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `backup_name` | string | ✅ | 备份文件名 |
| `dry_run` | bool | ❌ | 是否仅模拟恢复，默认 `false` |

```json
{
  "backup_name": "backup_20250610_095500.tar.gz",
  "dry_run": false
}
```

**响应** (200):

```json
{
  "status": "ok",
  "restored": true,
  "items_restored": {
    "data_files": 15,
    "config_files": 8
  }
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 400 | 缺少 `backup_name` |
| 404 | 备份文件不存在 |

---

### PUT /api/admin/logging/level

动态调整日志级别，无需重启服务。

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `level` | string | ✅ | 日志级别：`DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL` |

```json
{
  "level": "DEBUG"
}
```

**响应** (200):

```json
{
  "success": true,
  "level": "DEBUG"
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 400 | 缺少 `level` 或无效的日志级别 |

---

## 4. 人格 API

**源文件**: `app.py`

### GET /api/persona/list

列出所有人设配置。

**认证要求**: 无需认证

**响应** (200):

```json
{
  "personas": [
    {
      "id": "default",
      "name": "默认人设",
      "description": "温柔体贴的 AI 伴侣"
    },
    {
      "id": "cheerful",
      "name": "活泼开朗",
      "description": "充满活力的人设"
    }
  ],
  "total": 2
}
```

---

### PUT /api/persona/switch

运行时切换人设。

**认证要求**: 无需认证

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `persona_id` | string | ✅ | 目标人设 ID |

```json
{
  "persona_id": "cheerful"
}
```

**响应** (200):

```json
{
  "status": "ok",
  "active_id": "cheerful",
  "name": "活泼开朗"
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 400 | 缺少 `persona_id` |
| 404 | 人设不存在 |

---

### PUT /api/persona/stage

设置关系阶段，影响 AI 的交互风格和亲密度。

**认证要求**: 无需认证

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `stage` | string | ✅ | 关系阶段：`initial`、`familiar`、`intimate`、`deep` |

```json
{
  "stage": "familiar"
}
```

**响应** (200):

```json
{
  "status": "ok",
  "stage": "familiar"
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 400 | 缺少 `stage` |
| 404 | 无效的关系阶段 |

---

### POST /api/persona/reload

热重载人设配置文件，支持重载单个人设或全部人设。

**认证要求**: 无需认证

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `persona_id` | string | ❌ | 指定人设 ID 则重载单个，不指定则重载全部 |

```json
{
  "persona_id": "default"
}
```

**响应** (200):

```json
{
  "status": "ok",
  "reloaded": "default"
}
```

全部重载时：

```json
{
  "status": "ok",
  "reloaded": "all",
  "count": 3
}
```

---

## 5. Provider API

**源文件**: `app.py`

### GET /api/providers

查看所有 AI Provider 的状态和 AI 服务健康状况。

**认证要求**: 无需认证

**响应** (200):

```json
{
  "providers": [
    {
      "provider_id": "deepseek",
      "name": "DeepSeek",
      "adapter": "openai_compatible",
      "enabled": true,
      "default_model": "deepseek-chat"
    },
    {
      "provider_id": "openai",
      "name": "OpenAI",
      "adapter": "openai",
      "enabled": true,
      "default_model": "gpt-4o"
    }
  ],
  "ai_service_health": {
    "status": "ok",
    "active_provider": "deepseek"
  }
}
```

---

### GET /api/providers/{id}

查看单个 Provider 的详细配置。

**认证要求**: 无需认证

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | Provider ID |

**响应** (200):

```json
{
  "provider_id": "deepseek",
  "name": "DeepSeek",
  "adapter": "openai_compatible",
  "enabled": true,
  "default_model": "deepseek-chat",
  "embedding_model": "deepseek-embedding",
  "models": [
    {
      "id": "deepseek-chat",
      "type": "chat",
      "max_tokens": 8192,
      "dimension": null
    },
    {
      "id": "deepseek-embedding",
      "type": "embedding",
      "max_tokens": null,
      "dimension": 1536
    }
  ]
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | Provider 不存在 |

---

### PUT /api/providers/active

动态切换活跃 Provider（默认对话或 Embedding）。

**认证要求**: 无需认证

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `provider_id` | string | ✅ | 目标 Provider ID |
| `type` | string | ❌ | 切换类型：`default`（对话）或 `embedding`，默认 `default` |

```json
{
  "provider_id": "openai",
  "type": "default"
}
```

**响应** (200):

```json
{
  "status": "ok",
  "message": "Default provider switched to 'openai'",
  "provider_id": "openai",
  "default_model": "gpt-4o"
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 400 | 缺少 `provider_id` 或 Provider 已禁用 |
| 404 | Provider 不存在 |

---

### POST /api/providers/{id}/reload

热重载指定 Provider 的配置文件。

**认证要求**: 无需认证

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | Provider ID |

**响应** (200):

```json
{
  "status": "ok",
  "message": "Provider 'deepseek' reloaded"
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | Provider 不存在或配置文件缺失 |

---

## 6. 记忆 API

**源文件**: `app.py`

### GET /api/memory/{user_id}

获取指定用户的记忆数据，包括用户画像和事实记忆。

**认证要求**: 无需认证

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `user_id` | string | 用户 ID |

**响应** (200):

```json
{
  "profile": {
    "user_id": "u_abc123",
    "name": "Alice",
    "preferences": {
      "favorite_color": "蓝色",
      "hobby": "阅读"
    },
    "interaction_count": 42
  },
  "fact_memories": [
    {
      "id": "mem-001",
      "content": "用户喜欢在周末看电影",
      "importance": 0.85
    },
    {
      "id": "mem-002",
      "content": "用户养了一只叫小橘的猫",
      "importance": 0.92
    }
  ]
}
```

---

### GET /api/memory/graph

获取知识图谱数据，返回 ECharts graph 格式，可直接用于前端可视化渲染。

**认证要求**: 无需认证

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | string | — | 用户 ID，作为中心节点 |
| `depth` | int | 2 | 遍历深度（1-3） |
| `center_node_id` | string | — | 中心节点 ID（优先于 `user_id`） |

**响应** (200):

```json
{
  "nodes": [
    {
      "id": "user-001",
      "name": "Alice",
      "category": 0,
      "value": 1,
      "symbolSize": 40,
      "nodeType": "User",
      "properties": {"name": "Alice"},
      "isCenter": true
    },
    {
      "id": "entity-cat",
      "name": "小橘",
      "category": 1,
      "value": 1,
      "symbolSize": 24,
      "nodeType": "Entity",
      "properties": {"name": "小橘", "type": "pet"},
      "isCenter": false
    }
  ],
  "links": [
    {
      "source": "user-001",
      "target": "entity-cat",
      "relation": "owns"
    }
  ],
  "categories": [
    {"name": "User"},
    {"name": "Entity"},
    {"name": "Event"},
    {"name": "AIPersona"}
  ],
  "center_id": "user-001",
  "depth": 2
}
```

---

## 7. 主动陪伴 API

**源文件**: `app.py`

### GET /api/proactive/tasks

查看所有主动任务列表。

**认证要求**: 无需认证

**响应** (200):

```json
{
  "tasks": [
    {
      "task_id": "task-001",
      "name": "morning_greeting",
      "task_type": "cron",
      "trigger": "0 8 * * *",
      "priority": 5,
      "enabled": true,
      "next_run": "2025-06-11T08:00:00",
      "last_run": "2025-06-10T08:00:00"
    }
  ]
}
```

---

### POST /api/proactive/tasks

注册新的定时主动任务。

**认证要求**: 无需认证

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ❌ | 任务名称 |
| `trigger` | string | ✅ | Cron 表达式（如 `"0 9 * * *"`） |
| `task_type` | string | ❌ | 任务类型，默认 `"cron"` |
| `target_users` | string[] | ❌ | 目标用户 ID 列表 |
| `priority` | int | ❌ | 优先级，默认 5 |
| `max_retries` | int | ❌ | 最大重试次数，默认 3 |
| `metadata` | object | ❌ | 自定义元数据 |

```json
{
  "name": "evening_check",
  "trigger": "0 21 * * *",
  "task_type": "cron",
  "target_users": ["u_abc123"],
  "priority": 7,
  "metadata": {"action": "evening_greeting"}
}
```

**响应** (200):

```json
{
  "status": "created",
  "task_id": "task-002",
  "name": "evening_check",
  "next_run": "2025-06-10T21:00:00"
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 400 | 缺少 `trigger` |

---

### PUT /api/proactive/tasks/{id}

更新主动任务（启用/禁用/修改优先级）。

**认证要求**: 无需认证

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 任务 ID |

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `enabled` | bool | ❌ | 是否启用 |
| `priority` | int | ❌ | 优先级 |
| `name` | string | ❌ | 任务名称 |

```json
{
  "enabled": false,
  "priority": 3
}
```

**响应** (200):

```json
{
  "status": "updated",
  "task_id": "task-001",
  "enabled": false,
  "priority": 3,
  "next_run": null
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | 任务不存在 |

---

### GET /api/proactive/stats

查看主动交互系统的每日统计。

**认证要求**: 无需认证

**响应** (200):

```json
{
  "daily_stats": {
    "messages_sent": 15,
    "users_reached": 5,
    "tasks_executed": 20,
    "strategy_blocks": 3
  },
  "config": {
    "max_daily_messages": 10,
    "quiet_hours_start": 23,
    "quiet_hours_end": 8
  }
}
```

---

### POST /api/proactive/trigger

手动触发主动消息，受克制策略限制。

**认证要求**: 无需认证

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | ✅ | 目标用户 ID |
| `task_type` | string | ❌ | 任务类型，默认 `"greeting"` |
| `message` | string | ❌ | 自定义消息（不填则自动生成） |

```json
{
  "user_id": "u_abc123",
  "task_type": "greeting",
  "message": "今天辛苦了，早点休息哦~"
}
```

**响应** (200):

```json
{
  "status": "triggered",
  "user_id": "u_abc123",
  "task_type": "greeting",
  "message": "今天辛苦了，早点休息哦~"
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 400 | 缺少 `user_id` |
| 429 | 被克制策略拦截（安静时段或已达上限） |

---

## 8. TTS 语音合成 API

**源文件**: `app.py`

### POST /api/tts

文本转语音合成接口，返回音频文件。

**认证要求**: 无需认证

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | string | ✅ | 待合成文本 |
| `engine` | string | ❌ | TTS 引擎（如 `edge-tts`、`openai`） |
| `voice` | string | ❌ | 音色名称（如 `zh-CN-XiaoxiaoNeural`） |
| `persona_id` | string | ❌ | 人设 ID（使用人设关联的音色） |
| `rate` | float | ❌ | 语速倍率，默认 1.0 |
| `pitch` | float | ❌ | 音调倍率，默认 1.0 |
| `format` | string | ❌ | 输出格式，默认 `mp3` |

```json
{
  "text": "你好呀，今天过得怎么样？",
  "engine": "edge-tts",
  "voice": "zh-CN-XiaoxiaoNeural",
  "rate": 1.0
}
```

**响应** (200):

- `Content-Type: audio/mpeg`
- `Content-Disposition: inline; filename=tts.mp3`
- 响应体为音频二进制数据

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 400 | 缺少 `text` |
| 500 | TTS 合成失败 |

---

### GET /api/tts/voices

列出所有可用音色。

**认证要求**: 无需认证

**查询参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `engine` | string | 可选，按引擎名称过滤 |

**响应** (200):

```json
{
  "voices": [
    {
      "id": "zh-CN-XiaoxiaoNeural",
      "name": "Xiaoxiao",
      "language": "zh-CN",
      "gender": "Female"
    },
    {
      "id": "zh-CN-YunxiNeural",
      "name": "Yunxi",
      "language": "zh-CN",
      "gender": "Male"
    }
  ],
  "engines": ["edge-tts", "openai"]
}
```

---

### GET /api/tts/status

查看 TTS 系统整体状态。

**认证要求**: 无需认证

**响应** (200):

```json
{
  "engines": {
    "edge-tts": {"status": "ok", "voices_count": 300},
    "openai": {"status": "ok", "voices_count": 6}
  },
  "default_engine": "edge-tts"
}
```

---

## 9. 扩展与市场 API

**源文件**: `app.py`

### GET /api/extensions

列出已安装的扩展。

**认证要求**: 无需认证

**响应** (200):

```json
{
  "extensions": [
    {
      "id": "weather-plugin",
      "name": "天气插件",
      "version": "1.0.0",
      "description": "提供天气查询功能",
      "author": "YuanBot Team"
    }
  ],
  "count": 1
}
```

---

### GET /api/extensions/{id}

获取已安装扩展的详细信息。

**认证要求**: 无需认证

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 扩展 ID |

**响应** (200): 扩展 manifest 完整内容

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | 扩展不存在或缺少 manifest.json |

---

### POST /api/extensions/install

安装扩展（从 URL 下载 zip 或从本地路径安装）。

**认证要求**: 无需认证

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | ❌ | 扩展 zip 下载地址（与 `path` 二选一） |
| `path` | string | ❌ | 本地扩展目录路径（与 `url` 二选一） |
| `force` | bool | ❌ | 是否强制重装，默认 `false` |

```json
{
  "url": "https://example.com/weather-plugin-v1.0.0.zip"
}
```

**响应** (200):

```json
{
  "status": "installed",
  "extension": {
    "id": "weather-plugin",
    "name": "天气插件",
    "version": "1.0.0"
  }
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 400 | 未提供 `url` 或 `path`，或扩展验证失败 |
| 409 | 同版本已安装（使用 `force: true` 覆盖） |

---

### DELETE /api/extensions/uninstall

卸载已安装的扩展。

**认证要求**: 无需认证

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 扩展 ID |

```json
{
  "id": "weather-plugin"
}
```

**响应** (200):

```json
{
  "status": "uninstalled",
  "id": "weather-plugin"
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 400 | 缺少 `id` |
| 404 | 扩展不存在 |

---

### GET /api/marketplace/search

搜索社区扩展市场。

**认证要求**: 无需认证

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` | string | `""` | 搜索关键词 |
| `type` | string | `""` | 扩展类型过滤 |
| `limit` | int | 20 | 返回数量 |
| `offset` | int | 0 | 分页偏移 |

**响应** (200):

```json
{
  "extensions": [
    {
      "id": "weather-plugin",
      "name": "天气插件",
      "version": "1.0.0",
      "type": "tool",
      "description": "提供天气查询功能",
      "downloads": 1250,
      "rating": 4.5
    }
  ],
  "total": 1,
  "has_more": false
}
```

---

### GET /api/marketplace/extensions/{id}

获取市场扩展的详细信息。

**认证要求**: 无需认证

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 扩展 ID |

**响应** (200): 扩展完整信息

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | 市场中不存在该扩展 |

---

### POST /api/marketplace/extensions/{id}/install

从市场下载并安装扩展。

**认证要求**: 无需认证

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 扩展 ID |

**请求体**（可选）:

| 字段 | 类型 | 说明 |
|------|------|------|
| `force` | bool | 是否强制重装 |

**响应** (200):

```json
{
  "status": "installed",
  "extension_id": "weather-plugin",
  "manifest": {
    "id": "weather-plugin",
    "name": "天气插件",
    "version": "1.0.0"
  }
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | 市场中不存在该扩展 |
| 409 | 已安装（使用 `force: true` 覆盖） |

---

### DELETE /api/marketplace/extensions/{id}/uninstall

卸载通过市场安装的扩展。

**认证要求**: 无需认证

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | string | 扩展 ID |

**响应** (200):

```json
{
  "status": "uninstalled",
  "extension_id": "weather-plugin"
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 404 | 扩展未安装 |

---

## 10. GDPR API

**源文件**: `app.py`

### GET /api/gdpr/export

导出指定用户的所有数据（记忆、画像、对话历史），符合 GDPR 数据可携带权要求。

**认证要求**: 无需认证

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | ✅ | 用户 ID |

**响应** (200): 用户数据的 JSON 导出，包含记忆、画像、对话记录等完整数据

---

### DELETE /api/gdpr/delete

删除指定用户的所有数据，符合 GDPR 被遗忘权要求。需要显式确认。

**认证要求**: 无需认证

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | string | ✅ | 用户 ID |
| `confirm` | bool | ✅ | 必须为 `true` 才执行删除 |

```json
{
  "user_id": "u_abc123",
  "confirm": true
}
```

**响应** (200):

```json
{
  "status": "deleted",
  "items_deleted": {
    "memories": 42,
    "conversations": 15,
    "profile": true
  }
}
```

**错误响应**:

| 状态码 | 说明 |
|--------|------|
| 400 | 缺少 `user_id` 或 `confirm` 未设为 `true` |

---

## 11. 健康检查与监控

**源文件**: `app.py`

### GET /healthz

存活探针（Liveness Probe）。只要进程存活即返回 OK，不检查下游依赖。

**认证要求**: 无需认证

**响应** (200):

```json
{
  "status": "ok"
}
```

**用途**: Kubernetes `livenessProbe`

---

### GET /readyz

就绪探针（Readiness Probe）。检查所有关键依赖是否就绪，包括 AI 服务、主动调度器和事件引擎。

**认证要求**: 无需认证

**响应** (200 - 就绪):

```json
{
  "status": "ready",
  "checks": {
    "ai_service": {
      "status": "ok",
      "active_provider": "deepseek"
    },
    "proactive_scheduler": {
      "status": "ok",
      "task_count": 5
    },
    "event_engine": {
      "status": "ok",
      "trigger_count": 3
    }
  }
}
```

**响应** (503 - 未就绪):

```json
{
  "status": "not_ready",
  "checks": {
    "ai_service": {
      "status": "error",
      "error": "Connection refused"
    },
    "proactive_scheduler": {
      "status": "stopped",
      "task_count": 0
    },
    "event_engine": {
      "status": "ok",
      "trigger_count": 3
    }
  }
}
```

**用途**: Kubernetes `readinessProbe`

---

### GET /health

综合健康检查（向后兼容）。

**认证要求**: 无需认证

**响应** (200):

```json
{
  "status": "ok",
  "version": "1.5.0",
  "ai_service": {
    "status": "ok",
    "active_provider": "deepseek"
  }
}
```

---

### GET /metrics

Prometheus 格式的监控指标端点。

**认证要求**: 无需认证

**响应**: `Content-Type: text/plain; version=0.0.4; charset=utf-8`

暴露的指标包括：

| 指标名 | 类型 | 说明 |
|--------|------|------|
| `yuanbot_request_total` | Counter | 请求总数（按 method/endpoint/status 分组） |
| `yuanbot_request_duration_seconds` | Histogram | 请求延迟分布 |
| `yuanbot_active_connections` | Gauge | 当前活跃连接数 |
| `yuanbot_ai_call_total` | Counter | AI Provider 调用总数（按 provider/model/status 分组） |
| `yuanbot_ai_call_duration_seconds` | Histogram | AI 调用延迟分布 |
| `yuanbot_memory_operations_total` | Counter | 记忆操作总数（按 operation/memory_type 分组） |
| `yuanbot_proactive_tasks_executed_total` | Counter | 主动任务执行总数 |

**用途**: Prometheus 抓取、Grafana 可视化

---

## 12. WebSocket 端点

**源文件**: `app.py`

### /ws

通用 WebSocket 端点（无认证，向后兼容）。

**连接方式**:

```
ws://localhost:8000/ws
```

**认证要求**: 无需认证

**消息格式**: 由 WebAdapter 处理，兼容多种消息格式

---

### /ws/chat

认证聊天 WebSocket 端点，支持流式响应。

**连接方式**:

```
ws://localhost:8000/ws/chat?token=<jwt>
```

**认证要求**: 需要在 URL 参数中携带 JWT Token。未认证连接会被关闭（code: 4001）。

**客户端 → 服务端消息**:

| type | 说明 | 必填字段 |
|------|------|----------|
| `message` | 发送消息 | `text`，可选 `conversation_id` |
| `subscribe` | 订阅会话 | `conversation_id` |
| `ping` | 心跳 | — |

```json
{"type": "message", "text": "你好", "conversation_id": "conv-uuid-1234"}
```

```json
{"type": "subscribe", "conversation_id": "conv-uuid-1234"}
```

```json
{"type": "ping"}
```

**服务端 → 客户端消息**:

| type | 说明 | 字段 |
|------|------|------|
| `response` | 完整回复 | `text`, `conversation_id` |
| `stream_start` | 流式开始 | `conversation_id` |
| `stream_delta` | 流式增量 | `delta`（文本片段） |
| `stream_end` | 流式结束 | `conversation_id`, `full_text` |
| `subscribed` | 订阅确认 | `conversation_id` |
| `pong` | 心跳响应 | — |
| `error` | 错误 | `message` |

```json
{"type": "stream_start", "conversation_id": "conv-uuid-1234"}
```

```json
{"type": "stream_delta", "delta": "你好呀~"}
```

```json
{"type": "stream_delta", "delta": "今天过得怎么样？"}
```

```json
{"type": "stream_end", "conversation_id": "conv-uuid-1234", "full_text": "你好呀~ 今天过得怎么样？"}
```

---

### /ws/tts

TTS 流式音频合成 WebSocket 端点。

**连接方式**:

```
ws://localhost:8000/ws/tts?token=<jwt>
```

**认证要求**: 需要 JWT Token。未认证连接会被关闭（code: 4001）。

**客户端 → 服务端消息**:

| type | 说明 | 字段 |
|------|------|------|
| `synthesize` | 请求合成 | `text`（必填），`engine`、`voice`（可选） |
| `ping` | 心跳 | — |

```json
{"type": "synthesize", "text": "你好世界", "engine": "edge-tts", "voice": "zh-CN-XiaoxiaoNeural"}
```

**服务端 → 客户端消息**:

| type | 说明 | 字段 |
|------|------|------|
| `audio_start` | 音频开始 | `format`（如 `"mp3"`） |
| `audio_chunk` | 音频块 | `data`（Base64 编码的音频数据） |
| `audio_end` | 音频结束 | `chunks`（总块数） |
| `error` | 错误 | `message` |
| `pong` | 心跳响应 | — |

```json
{"type": "audio_start", "format": "mp3"}
```

```json
{"type": "audio_chunk", "data": "SUQzBAAAAAAAI1RTU0UAAA..."}
```

```json
{"type": "audio_end", "chunks": 15}
```

---

### /ws/logs

实时日志流 WebSocket 端点（仅管理员）。

**连接方式**:

```
ws://localhost:8000/ws/logs?token=<jwt>
```

**认证要求**: 需要 JWT Token 且用户角色为 `admin`。非管理员连接会被关闭（code: 4003）。

**服务端 → 客户端消息**（每 5 秒推送）:

```json
{
  "type": "log",
  "level": "info",
  "message": "CPU: 12.5% | Memory: 45.2%",
  "timestamp": "2025-06-10T09:55:00"
}
```

---

## 错误码汇总

| 状态码 | 含义 | 常见场景 |
|--------|------|----------|
| 200 | 成功 | 正常请求 |
| 400 | 请求参数错误 | 缺少必填字段、参数格式错误 |
| 401 | 未认证 | Token 无效或过期 |
| 403 | 权限不足 | 非管理员访问管理接口 |
| 404 | 资源不存在 | 会话/用户/Provider 不存在 |
| 409 | 资源冲突 | 用户名重复、扩展已安装 |
| 429 | 请求被限流 | 主动消息被克制策略拦截 |
| 500 | 服务器内部错误 | TTS 合成失败等 |
| 503 | 服务不可用 | 就绪探针检查失败 |
