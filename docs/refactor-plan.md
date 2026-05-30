# 目录重构计划

> 分支: `refactor/project-structure`
> 目标: 对齐 conformance-report-v2 中定义的目标目录结构

## 重构映射

### Batch 1: `channels/` → `gateway/` + `adapters/channel/`

**gateway/** (网关核心):
- `channels/gateway.py` → `gateway/gateway.py`
- `channels/manager.py` → `gateway/adapter_manager.py`
- `channels/identity.py` → `gateway/identity_service.py`
- `channels/push.py` → `gateway/push_dispatcher.py`
- `channels/auth.py` → `gateway/auth.py`
- `channels/privacy.py` → `gateway/privacy.py`
- `channels/jwt_auth.py` → `gateway/jwt_auth.py`

**adapters/channel/** (通道适配器):
- `channels/base.py` → `adapters/channel/base.py`
- `channels/telegram.py` → `adapters/channel/telegram_adapter.py`
- `channels/discord.py` → `adapters/channel/discord_adapter.py`
- `channels/wecom.py` → `adapters/channel/wecom_adapter.py`
- `channels/web.py` → `adapters/channel/web_adapter.py`
- `channels/qq.py` → `adapters/channel/qq_adapter.py`
- `channels/wechat.py` → `adapters/channel/wechat_adapter.py`
- `channels/weixin_cdn.py` → `adapters/channel/weixin_cdn.py`

### Batch 2: `providers/` → `adapters/ai/` + `services/`

**adapters/ai/** (AI 适配器):
- `providers/base.py` → `adapters/ai/base.py`
- `providers/openai_adapter.py` → `adapters/ai/openai_adapter.py`
- `providers/anthropic_adapter.py` → `adapters/ai/anthropic_adapter.py`
- `providers/deepseek_adapter.py` → `adapters/ai/deepseek_adapter.py`
- `providers/ollama_adapter.py` → `adapters/ai/ollama_adapter.py`

**services/** (服务层):
- `providers/service.py` → `services/ai_service.py`

**providers/** (保留):
- `providers/manager.py` → 保留
- `providers/registry.py` → 保留

### Batch 3: `capabilities/` → `services/` + `tools/` + `skills/`

**services/**:
- `capabilities/orchestrator.py` → `services/capability_orchestrator.py`
- `capabilities/extension_standard.py` → `services/extension_standard.py`

**tools/**:
- `capabilities/tool_manager.py` → `tools/manager.py`
- `capabilities/builtin_tools.py` → `tools/builtin.py`
- `capabilities/sandbox.py` → `tools/sandbox.py`
- `capabilities/grpc_sandbox.py` → `tools/grpc_sandbox.py`

**skills/**:
- `capabilities/skill_manager.py` → `skills/manager.py`

### Batch 4: `infrastructure/serverless.py` → `deployment/serverless.py`
