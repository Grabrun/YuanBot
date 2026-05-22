# API 参考

YuanBot 提供 RESTful API 和 WebSocket 接口，用于对话、数据查询和系统管理。

**基础 URL**: `http://localhost:8000`

---

## 认证方式

当前版本的 API 默认无需认证（本地部署场景）。如需在公网暴露，建议：

1. 使用 Nginx 反向代理并配置 Basic Auth 或 JWT
2. 通过环境变量 `YUANBOT_API_KEY` 设置 API Key 认证
3. 使用 Kubernetes Ingress 配置 TLS 和认证

---

## 健康检查端点

### GET /healthz

Liveness probe — 检查服务是否存活。

**响应**:

```json
{
  "status": "ok"
}
```

**状态码**: 200

**用途**: Kubernetes `livenessProbe`

---

### GET /readyz

Readiness probe — 检查所有关键依赖是否就绪。

**响应** (200 - 就绪):

```json
{
  "status": "ready",
  "checks": {
    "ai_service": {
      "status": "ok",
      "provider": "openai",
      "model": "gpt-4o"
    },
    "proactive_scheduler": {
      "status": "ok",
      "task_count": 3
    },
    "event_engine": {
      "status": "ok",
      "trigger_count": 5
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
      "status": "stopped",
      "trigger_count": 0
    }
  }
}
```

**状态码**: 200（就绪）/ 503（未就绪）

**用途**: Kubernetes `readinessProbe`

---

### GET /health

健康检查（向后兼容端点）。

**响应**:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "ai_service": {
    "status": "ok",
    "provider": "openai",
    "model": "gpt-4o"
  }
}
```

**状态码**: 200

---

## 监控端点

### GET /metrics

Prometheus 格式的监控指标。

**响应**: Prometheus text format

```
# HELP yuanbot_request_total Total request count
# TYPE yuanbot_request_total counter
yuanbot_request_total{method="GET",endpoint="/healthz",status="200"} 42.0

# HELP yuanbot_request_duration_seconds Request latency in seconds
# TYPE yuanbot_request_duration_seconds histogram
yuanbot_request_duration_seconds_bucket{method="GET",endpoint="/healthz",le="0.01"} 40.0

# HELP yuanbot_active_connections Number of active connections
# TYPE yuanbot_active_connections gauge
yuanbot_active_connections 3.0

# HELP yuanbot_ai_call_total Total AI provider call count
# TYPE yuanbot_ai_call_total counter
yuanbot_ai_call_total{provider="openai",model="gpt-4o",status="success"} 156.0

# HELP yuanbot_ai_call_duration_seconds AI provider call latency
# TYPE yuanbot_ai_call_duration_seconds histogram
yuanbot_ai_call_duration_seconds_bucket{provider="openai",model="gpt-4o",le="1.0"} 120.0

# HELP yuanbot_memory_operations_total Total memory operations
# TYPE yuanbot_memory_operations_total counter
yuanbot_memory_operations_total{operation="store",memory_type="fact"} 89.0

# HELP yuanbot_proactive_tasks_executed_total Total proactive tasks executed
# TYPE yuanbot_proactive_tasks_executed_total counter
yuanbot_proactive_tasks_executed_total{task_name="greeting",status="success"} 23.0
```

**Content-Type**: `text/plain; version=0.0.4; charset=utf-8`

---

## 对话接口

### POST /api/chat

发送文本消息并获取 AI 回复。

**请求体**:

```json
{
  "user_id": "user_123",
  "message": "你好，今天天气怎么样？"
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `user_id` | string | ❌ | 用户标识（默认 `"anonymous"`） |
| `message` | string | ✅ | 消息文本 |

**响应**:

```json
{
  "content": "你好！今天天气不错呢～你想查哪个城市的天气呀？",
  "proactive_followups": [
    {
      "task_type": "care",
      "scheduled_at": "2024-01-15T18:00:00",
      "content_hint": "询问用户一天过得如何",
      "priority": 1
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | string | AI 回复文本 |
| `proactive_followups` | array | 后续主动交互任务列表 |

**状态码**: 200

**示例**:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "message": "你好"
  }'
```

---

### WebSocket /ws

实时双向聊天通道。

**连接地址**: `ws://localhost:8000/ws`

**消息格式**:

发送消息：

```json
{
  "type": "message",
  "text": "你好"
}
```

心跳检测：

```json
{
  "type": "ping"
}
```

接收响应：

```json
{
  "type": "response",
  "content": "你好！有什么我可以帮你的吗？",
  "metadata": {}
}
```

**JavaScript 示例**:

```javascript
const ws = new WebSocket("ws://localhost:8000/ws");

ws.onopen = () => {
  console.log("已连接");
  ws.send(JSON.stringify({
    type: "message",
    text: "你好"
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log("收到回复:", data.content);
};

ws.onclose = () => {
  console.log("连接已关闭");
};
```

---

## 数据查询接口

### GET /api/memory/{user_id}

查看指定用户的记忆数据。

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `user_id` | string | 用户 ID |

**响应**:

```json
{
  "profile": {
    "user_id": "user_123",
    "display_name": "小明",
    "preferences": {
      "favorite_color": "blue",
      "dislikes": ["香菜"]
    },
    "relationship_stage": "familiar",
    "trust_score": 0.6,
    "total_interactions": 42,
    "first_interaction": "2024-01-01T10:00:00",
    "last_interaction": "2024-01-15T15:30:00"
  },
  "fact_memories": [
    {
      "id": "mem_001",
      "content": "用户喜欢蓝色",
      "importance": 0.8
    },
    {
      "id": "mem_002",
      "content": "用户不喜欢香菜",
      "importance": 0.6
    }
  ]
}
```

**状态码**: 200

---

### GET /api/proactive/tasks

查看主动交互任务列表。

**响应**:

```json
{
  "tasks": [
    {
      "task_id": "task_001",
      "name": "早安问候",
      "task_type": "greeting",
      "trigger": "cron: 0 8 * * *",
      "priority": 1,
      "enabled": true,
      "next_run": "2024-01-16T08:00:00",
      "last_run": "2024-01-15T08:00:00"
    },
    {
      "task_id": "task_002",
      "name": "静默关怀",
      "task_type": "care",
      "trigger": "event: silence_24h",
      "priority": 2,
      "enabled": true,
      "next_run": null,
      "last_run": null
    }
  ]
}
```

**状态码**: 200

---

### GET /api/proactive/stats

查看主动交互统计信息。

**响应**:

```json
{
  "daily_stats": {
    "date": "2024-01-15",
    "greetings_sent": 2,
    "care_messages_sent": 1,
    "total_interactions": 5,
    "last_interaction": "2024-01-15T15:30:00"
  },
  "config": {
    "enabled": true,
    "greeting_enabled": true,
    "frequency": "medium",
    "max_per_day": 5
  }
}
```

**状态码**: 200

---

### GET /api/providers

查看 AI 提供商状态。

**响应**:

```json
{
  "providers": [
    {
      "provider_id": "openai",
      "enabled": true,
      "default_model": "gpt-4o",
      "model_count": 3
    },
    {
      "provider_id": "claude",
      "enabled": true,
      "default_model": "claude-sonnet-4-20250514",
      "model_count": 2
    }
  ],
  "ai_service_health": {
    "status": "ok",
    "provider": "openai",
    "model": "gpt-4o"
  }
}
```

**状态码**: 200

---

### GET /api/capabilities

查看已加载的 Skills 和 Tools。

**响应**:

```json
{
  "skills": [
    {
      "skill_id": "daily_chat",
      "name": "日常闲聊",
      "category": "daily_chat",
      "enabled": true
    },
    {
      "skill_id": "emotional_comfort",
      "name": "情绪安抚",
      "category": "emotional_care",
      "enabled": true
    }
  ],
  "tools": [
    {
      "tool_id": "get_weather",
      "name": "天气查询",
      "permission_level": "readonly",
      "enabled": true
    },
    {
      "tool_id": "set_reminder",
      "name": "设置提醒",
      "permission_level": "readonly",
      "enabled": true
    }
  ]
}
```

**状态码**: 200

---

## 扩展管理接口

### GET /api/extensions

列出已安装的扩展。

**响应**:

```json
{
  "extensions": [
    {
      "id": "my-skill",
      "name": "自定义技能",
      "type": "skill",
      "version": "1.0.0",
      "description": "一个自定义技能",
      "license": "MIT"
    }
  ],
  "count": 1
}
```

**状态码**: 200

---

### GET /api/extensions/{ext_id}

获取扩展详情。

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `ext_id` | string | 扩展 ID |

**响应** (200):

```json
{
  "id": "my-skill",
  "name": "自定义技能",
  "type": "skill",
  "version": "1.0.0",
  "description": "一个自定义技能",
  "license": "MIT",
  "author": {
    "name": "开发者",
    "email": "dev@example.com"
  },
  "keywords": ["chat", "custom"]
}
```

**响应** (404):

```json
{
  "error": "Extension 'my-skill' not found"
}
```

**状态码**: 200 / 404

---

### POST /api/extensions/install

安装扩展。

**请求体** (从 URL 安装):

```json
{
  "url": "https://example.com/my-extension.yuanbot"
}
```

**请求体** (从本地路径安装):

```json
{
  "path": "/path/to/extension"
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `url` | string | 二选一 | 扩展 zip 下载地址 |
| `path` | string | 二选一 | 本地扩展目录路径 |

**响应** (200):

```json
{
  "status": "installed",
  "extension": {
    "id": "my-skill",
    "name": "自定义技能",
    "type": "skill",
    "version": "1.0.0"
  }
}
```

**响应** (400):

```json
{
  "error": "Must provide either 'url' or 'path'"
}
```

**状态码**: 200 / 400

---

### POST /api/extensions/uninstall

卸载扩展。

**请求体**:

```json
{
  "id": "my-skill"
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 扩展 ID |

**响应** (200):

```json
{
  "status": "uninstalled",
  "id": "my-skill"
}
```

**响应** (404):

```json
{
  "error": "Extension 'my-skill' not found"
}
```

**状态码**: 200 / 400 / 404

---

## GDPR 合规接口

### GET /api/gdpr/export

导出指定用户的所有数据（符合 GDPR 数据可携带权）。

**查询参数**:

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `user_id` | string | ✅ | 用户 ID |

**响应**:

```json
{
  "user_id": "user_123",
  "export_date": "2024-01-15T15:30:00",
  "profile": {
    "display_name": "小明",
    "preferences": {},
    "relationship_stage": "familiar"
  },
  "fact_memories": [],
  "episodic_memories": [],
  "semantic_memories": [],
  "emotion_records": [],
  "interaction_history": []
}
```

**状态码**: 200

---

### POST /api/gdpr/delete

删除指定用户的所有数据（符合 GDPR 被遗忘权）。

**请求体**:

```json
{
  "user_id": "user_123",
  "confirm": true
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `user_id` | string | ✅ | 用户 ID |
| `confirm` | bool | ✅ | 确认删除（必须为 `true`） |

**响应** (200):

```json
{
  "status": "deleted",
  "user_id": "user_123",
  "deleted_records": {
    "fact_memories": 5,
    "episodic_memories": 12,
    "semantic_memories": 3,
    "emotion_records": 20,
    "profile": true
  }
}
```

**响应** (400 - 未确认):

```json
{
  "error": "Confirmation required",
  "hint": "Set 'confirm': true in request body to proceed with data deletion."
}
```

**响应** (400 - 缺少 user_id):

```json
{
  "error": "user_id is required"
}
```

**状态码**: 200 / 400

---

## 错误码说明

| HTTP 状态码 | 说明 |
|-------------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |
| 503 | 服务不可用（readiness probe 失败） |

### 错误响应格式

所有错误响应均遵循以下格式：

```json
{
  "error": "错误描述",
  "detail": "详细信息（可选）",
  "hint": "解决建议（可选）"
}
```

---

## 请求限制

| 端点 | 限制 | 说明 |
|------|------|------|
| `/api/chat` | 30 次/分钟 | 可通过配置调整 |
| `/api/memory/*` | 无限制 | 建议生产环境加限流 |
| `/api/extensions/install` | 无限制 | 建议生产环境加认证 |
| WebSocket | 无消息频率限制 | 由连接本身限制 |

---

## 请求/响应示例

### 完整对话流程

```bash
# 1. 发送第一条消息
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "message": "你好，我叫小明"}'

# 响应
# {"content": "你好小明！很高兴认识你～", "proactive_followups": []}

# 2. 继续对话
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "message": "今天心情不太好"}'

# 响应
# {"content": "怎么了小明？愿意跟我说说吗？我会陪着你的...", "proactive_followups": [...]}

# 3. 查看记忆
curl http://localhost:8000/api/memory/alice

# 4. 查看主动任务
curl http://localhost:8000/api/proactive/tasks
```
