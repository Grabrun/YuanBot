# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.2.1] - 2026-06-14

### 🐛 修复

- **CI/CD**: 修复 GitHub Actions workflow 分支名 main→master（此前从未触发）
- **Ruff lint**: 修复 tests/ 和 scripts/ 中 84 处 lint 错误（未使用导入、行过长等）
- **默认模型**: config.py AiConfig 和 AIProviderConfig 默认模型 gpt-4o → gpt-5.4
- **测试断言**: test_config.py 更新为最新模型名和数量
- **安装文档**: 全部 md 文件 pip install yuanbot → git clone + venv 源码安装
- **VitePress 文档站**: 修复语言切换开关（禁用旧 MkDocs 防覆盖）

### 📖 文档

- **所有安装文档重写**: docs/ + docs-vitepress/（中/英/日）统一使用源码安装
- **供应商配置**: 9 家 AI 提供商模型更新至最新版（含退役警告）
- **README**: 全面重构，更新测试数据、供应商表等

### 🎨 样式

- **ruff format**: 51 个源文件统一格式化

---

## [1.2.0] - 2026-06-14

### ✨ 新增功能

#### 用户界面系统
- **人格商店 WebUI** — `PersonaStoreView.vue` (457行)，支持"我的人设"/"商店"双Tab、卡片网格、详情抽屉、一键安装/激活/删除
- **记忆图谱可视化** — `MemoryView.vue` ECharts 力导向图渲染，节点按类型着色，支持拖拽/缩放/搜索
- **扩展市场 WebUI** — `MarketplaceView.vue` (562行)，搜索/分类筛选/卡片展示/详情抽屉/评分评论/安装卸载
- **流式播放同步 (WebSocket TTS)** — `/ws/tts` 端点 + ChatBubble 语音播放按钮 + Web Audio API
- **本地意图分类模型** — `MLIntentClassifier`，ONNX 模型本地运行，无需外部 API

#### 人格与决策系统
- **多人设运行时切换** — `PersonaManager` + `YamlPersona`，YAML 配置加载 + 运行时切换
- 内置 3 个示例人设：cheerful（小晴）、mentor（明远）、gentle（静安）
- CLI 命令：`yuanbot persona list|info|switch|stage`
- REST API：/api/persona/list /switch /stage /reload
- 20 个人设管理器测试
- **深度情感分析** — `DeepEmotionAnalyzer`，LLM 链式思考模式
- **关系阶段动态调整** — 4阶段：初期→熟悉→亲密→深度

#### 备份与扩展市场
- **备份/恢复系统** — `BackupManager`（tar.gz + meta.json），支持选择性恢复、自动清理
- CLI 命令：`yuanbot backup create|list|info|delete|cleanup|restore`
- REST API 统一的备份管理端点
- 16 个备份系统测试
- **社区扩展市场** — `MarketplaceClient`（注册表搜索、缓存、下载）
- CLI 命令：`yuanbot search|install|marketplace`
- REST API 市场端点 + 离线缓存自动降级
- 14 个市场客户端测试

#### 性能优化
- **工具调用并行执行** — 多工具同时运行，互不阻塞
- **事件引擎并行化** — 循环并行处理，触发器预索引，最近事件上限
- **SQLite 复合索引** — 关键查询路径索引优化
- **记忆冲突检测 DB 级过滤** — 数据库层去重减少内存开销
- **批量异步操作** — TTS、Provider 提供商、事件引擎批量处理
- **热路径优化** — should_send 交互计数修复 + frozenset 常量优化

#### 可观测性
- **日志聚合运维系统** — Loki + Promtail + Grafana 全栈配置
- 预置 Grafana 日志监控仪表盘
- Prometheus 监控指标 `/metrics`（请求计数、延迟、AI调用、记忆操作）
- 健康检查端点 `/healthz` 和 `/readyz`（Kubernetes 探针规范）
- 配置热加载（Providers/Channels 配置变化自动重载适配器）

#### 安全与合规
- JWT 权限令牌（gateway/jwt_auth.py，支持 readonly/user_data/system）
- GDPR 数据导出/删除 API（/api/gdpr/export、/api/gdpr/delete）
- CSRF 全链路保护（随机 Token + hash_equals 时间安全比较）
- AI 适配器速率限制（token bucket 算法）

#### 存储引擎
- Milvus Lite 向量数据库集成（自动检测，fallback 内存模式）
- Kuzu 嵌入式图数据库集成（知识图谱持久化）
- MySQL 存储支持（SQLite/MySQL 无缝切换）
- Redis 工作记忆自动启用
- 记忆整理定时调度（记忆固化 + 遗忘曲线 Cron 任务）

#### 部署与扩展
- Serverless 部署模式（AWS Lambda / 阿里云 FC handler）
- gRPC 工具沙盒框架（proto 定义 + server/client stub）
- yuanbot-cli 完整命令：`create|validate|test|build|publish|search|install`
- Docker Compose 一站式部署（含 Loki + Grafana + Promtail）

### 🧪 开发者工具（P3 增强项）
- **yuanbot-testkit 测试框架** — `MockCore` + `TestAdapter` 包
  - `MockCore`：模拟 AI 对话、嵌入、记忆、工具执行，支持调用记录与断言
  - `TestAdapter`：模拟通道消息收发，支持回调注册、消息记录
  - 8 个开箱即用的 pytest fixtures，41 个专用测试
  - `pip install -e ".[test]"` 即可安装
- **VitePress 多语言文档站** — `docs-vitepress/`，中文（完整）、英文/日文（WIP）
  - `npx vitepress build` 成功构建，GitHub Actions 自动部署
- **社区贡献 CI/CD 流水线**
  - PR 自动审查（`pr-review.yml`）：变更分类、风险检测、自动标签
  - CI 扩展验证（`ci.yml`）：manifest.json 校验、接口完整性检查、安全扫描
  - 自动发布（`publish.yml`）：GitHub Release + Docker 镜像 + 版本标签
- **CONTRIBUTING.md** 全面重写（386行），含 PR 流程、扩展开发、贡献清单

### 📊 测试
- 总计 **1453 个测试通过**（+374 自 v1.1.1）
- 41 个 testkit 专项测试覆盖 MockCore / TestAdapter / Fixtures
- Ruff lint 全通过：0 个 RUF100/F/PERF/SIM/C4/B 问题

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
