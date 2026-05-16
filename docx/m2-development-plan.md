# 缘·Bot (YuanBot) M2 开发计划

## 目标

完成基础适配器层，实现 OpenAI/Claude 双 AI 提供商 + Telegram/Web 双消息通道。

## 交付物

| 模块 | 文件 | 说明 |
|------|------|------|
| Claude 适配器 | `adapters/ai/anthropic_adapter.py` | Anthropic Claude API 适配器 |
| Web 通道适配器 | `adapters/channel/web_adapter.py` | WebSocket 实时聊天通道 |
| 配置示例 | `configs/default.yaml` | 更新多适配器配置 |
| 测试 | `tests/test_adapters/` | 适配器单元测试 |

## 技术要点

### Claude 适配器
- 使用 Anthropic Messages API（非 Chat Completions）
- 系统提示词独立传递
- 工具调用使用 `tool_use` / `tool_result` 格式
- 流式响应使用 SSE

### Web 通道适配器
- 基于 FastAPI WebSocket
- JSON 消息协议
- 心跳保活（ping/pong）
- 会话管理（session_id）

## 验收标准

1. Claude 适配器能正常调用 API 并返回标准化 `ChatResponse`
2. Web 客户端能通过 WebSocket 实时对话
3. 所有测试通过
4. 代码风格一致（ruff check 无报错）
