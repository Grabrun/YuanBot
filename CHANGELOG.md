# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.2.0] - 2026-05-30

### ✨ 新增功能

#### P1 功能实现

##### 备份/恢复系统
- 新增 `BackupManager` 备份管理器（tar.gz 归档格式 + meta.json 元数据）
- CLI 命令：`yuanbot backup create|list|info|delete|cleanup`
- CLI 命令：`yuanbot restore <name> [--dry-run] [--no-data] [--no-configs]`
- REST API 统一使用 BackupManager（`/api/admin/backup`、`/api/admin/backups`、`/api/admin/restore`）
- 支持试运行模式、选择性恢复、自动清理旧备份
- 16 个备份系统测试

##### 社区扩展市场
- 新增 `MarketplaceClient` 市场客户端（注册表搜索、缓存、下载）
- CLI 命令：`yuanbot search <query> [--type] [--limit]`
- CLI 命令：`yuanbot install <ext_id> [--version] [--force]`
- CLI 命令：`yuanbot marketplace categories|refresh`
- REST API：`/api/marketplace/search`、`/api/marketplace/extensions`、`/api/marketplace/extensions/{id}`、`/api/marketplace/categories`、`/api/marketplace/refresh`
- 离线缓存 + 自动降级
- 14 个市场客户端测试

##### 多人设运行时切换
- 新增 `PersonaManager` 人设管理器（YAML 配置加载 + 运行时切换）
- 新增 `YamlPersona` 动态人设（支持自定义 prompt、行为规则、语音风格、阶段覆盖）
- CLI 命令：`yuanbot persona list|info|switch|stage`
- REST API：`/api/persona`、`/api/persona/list`、`/api/persona/switch`、`/api/persona/stage`、`/api/persona/reload`
- 内置 3 个示例人设：cheerful（小晴）、mentor（明远）、gentle（静安）
- 人设切换自动同步编排引擎
- 20 个人设管理器测试

### 📊 测试
- 总计 1079 个测试通过（新增 50 个）
- 3 个跳过，14 个 warnings

## [1.1.1] - 2026-05-29

### 🐛 修复

- 修复 `app.py` WebSocket 路由中 `logger` 未定义导致的运行时 NameError (F821)
- 修复 AI 适配器 `base.py` 中敏感字段过滤逻辑行过长问题
- 修复 `auth/store.py`、`cli.py` 等文件 Ruff lint 行过长问题
- 自动修复 23 个 Ruff lint 问题（未使用导入、导入排序、f-string 等）
- 将 `bcrypt` 和 `PyJWT` 加入 dev 依赖，避免新环境测试收集失败
- 补全测试依赖，全部 877 个测试通过

## [1.1.0] - 2026-05-22

### ✨ 新增功能

#### 存储引擎升级
- Milvus Lite 向量数据库真正集成（自动检测，fallback 内存模式）
- Kuzu 嵌入式图数据库真正集成（知识图谱持久化）
- MySQL 存储支持（SQLite/MySQL 无缝切换）
- Redis 工作记忆自动启用（环境变量检测，自动降级）

#### 监控与运维
- Prometheus 监控指标 `/metrics`（请求计数、延迟、AI调用、记忆操作）
- 健康检查端点 `/healthz` 和 `/readyz`（Kubernetes 探针规范）
- 配置热加载（Providers/Channels 配置变化自动重载适配器）

#### 安全与合规
- JWT 权限令牌（gateway/jwt_auth.py，支持 readonly/user_data/system）
- GDPR 数据导出/删除 API（/api/gdpr/export、/api/gdpr/delete）
- AI 适配器 validate_config() 方法
- AI 适配器速率限制（token bucket 算法）

#### AI 增强
- 深度情感分析（DeepEmotionAnalyzer，LLM 链式思考模式）
- 本地小模型意图识别（MLIntentClassifier，ONNX 模型支持）
- 关系阶段动态调整（4阶段：初期→熟悉→亲密→深度）
- 记忆整理定时调度（记忆固化 + 遗忘曲线 Cron 任务）

#### 部署与扩展
- Serverless 部署模式（AWS Lambda / 阿里云 FC handler）
- 扩展市场基础 API（/api/extensions CRUD）
- gRPC 工具沙盒框架（proto 定义 + server/client stub）
- yuanbot-cli 完整命令（create/validate/test/build/publish）

#### 文档
- 完整使用文档（快速开始、配置、API、部署、开发指南）
- 架构详解、贡献指南
- 设计检查报告（4轮迭代）

### 📊 测试
- 787 个测试全部通过

---

## [1.0.0] - 2026-05-22

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
