# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2025-05-22

### 🎉 首个正式发布

#### 核心架构

- 分层架构：网关层 → 适配器层 → 编排层 → 服务层 → 基础设施层
- 统一网关 (YuanGateway)：入口收敛、认证鉴权、限流、身份映射
- 编排引擎 (OrchestratorEngine)：意图识别 → 上下文构建 → 对话决策 → 能力编排

#### AI 提供商适配器

- OpenAI 适配器（GPT-4o、GPT-4 等）
- Anthropic Claude 适配器（Claude 3.5 Sonnet 等）
- DeepSeek 适配器
- Ollama 适配器（本地模型）
- 支持流式输出、工具调用、多模态

#### 消息通道适配器

- Telegram 适配器
- Discord 适配器
- 企业微信适配器
- WebChat 适配器（含 WebSocket）

#### 记忆系统

- 三层记忆架构：工作记忆、情景记忆、事实记忆
- 向量语义检索（Qdrant）
- 情感趋势追踪 (EmotionTracker)
- 自动记忆衰减与巩固

#### 人格系统

- 模块化人格引擎：情感、意图、对话决策、上下文构建
- Token 预算管理
- YAML 配置驱动，运行时可切换

#### 主动陪伴系统

- 定时任务调度 (ProactiveScheduler)
- 基于上下文的主动消息策略 (ProactiveStrategy)
- 事件触发引擎 (EventEngine)

#### 能力系统

- 技能管理 (SkillManager)
- 工具管理 (ToolManager)
- 能力编排 (CapabilityOrchestrator)
- gRPC 沙箱 (安全工具执行)

#### 基础设施

- SQLite / MySQL 数据存储
- Redis 缓存与事件队列
- Qdrant 向量存储
- Neo4j 图存储（可选）
- 配置热加载 (ConfigWatcher)

#### API 端点

- 健康检查：`/healthz`、`/readyz`
- 对话接口：`/api/chat`、`/ws` (WebSocket)
- 记忆查询：`/api/memory/{user_id}`
- 提供商状态：`/api/providers`
- 能力查看：`/api/capabilities`
- 主动任务：`/api/proactive/tasks`、`/api/proactive/stats`
- GDPR 合规：`/api/gdpr/export`、`/api/gdpr/delete`
- 扩展市场：`/api/extensions`、安装/卸载
- 监控指标：`/metrics` (Prometheus)

#### 部署

- Docker + docker-compose 支持
- Kubernetes 部署配置
- Serverless 部署支持（Mangum）
- Prometheus 监控指标

#### 开发工具

- CLI 入口 (`yuanbot` 命令)
- 扩展脚手架生成器
- 完整的测试套件 (739 测试用例)
- CI/CD (GitHub Actions)
- Ruff 代码质量检查

#### 文档

- 架构详解 (`docs/architecture.md`)
- 开发指南 (`docs/development.md`)
- 贡献指南 (`CONTRIBUTING.md`)
- 详细设计文档（AI 提供商、记忆系统、人格系统等）
