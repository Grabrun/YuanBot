🌸 缘·Bot 能力与工具扩展系统详细设计文档 (v1.4)

版本历史

版本 日期 修改内容
v1.0 2026-05-17 初始详细设计，基于总体架构 v1.4

---

1. 系统定位与目标

能力与工具扩展系统是 缘·Bot 的“手足与技能包”，负责定义、管理、安全地执行 AI 伴侣的各类能力。它使角色不仅能“说话”，更能“做事”——从搜索信息、设定提醒到创作故事、安抚情绪，所有能力均以模块化、可插拔的形式动态加载。

核心目标：

· 能力解耦：Skills 与 Tools 独立于核心编排层和人格配置，可自由增删。
· 按需加载：通过三层渐进式加载策略，将 Token 消耗降至最低，避免上下文污染。
· 安全隔离：所有外部调用型 Tools 在沙盒中执行，杜绝任意代码执行风险。
· 标准化扩展：基于 Y.E.S. 规范，社区可快速开发、分享新的能力模块。
· 人格驱动选择：由决策系统根据角色人设和能力域声明，智能决定当前场景下可用的能力集合。

---

2. 系统架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                   能力与工具扩展系统                           │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐ │
│  │ 能力注册中心 │  │ 动态加载器   │  │ 执行沙盒管理器       │ │
│  │ Registry    │  │ Loader      │  │ Sandbox Manager      │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬───────────┘ │
│         │                │                     │              │
│  ┌──────▼────────────────▼─────────────────────▼──────────┐ │
│  │                  能力管理层                               │ │
│  │                                                          │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐ │ │
│  │  │ Skills Pool  │  │  Tools Pool  │  │ Capability     │ │ │
│  │  │ (软能力)     │  │  (硬能力)    │  │ Domain Matcher │ │ │
│  │  └──────────────┘  └──────────────┘  └───────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                  工具执行沙盒层                            │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐               │ │
│  │  │ Docker   │  │  WASM    │  │ 本地受限  │               │ │
│  │  │ Sandbox  │  │  Sandbox │  │ 线程池   │               │ │
│  │  └──────────┘  └──────────┘  └──────────┘               │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │          统一能力 API (Capability API)                    │ │
│  │  · register()  · load_for_intent()  · execute_tool()    │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

设计原则：

· 定义与执行分离：Skill/Tool 的定义仅是声明，执行由独立的环境承载。
· Agent 无感：决策系统仅需声明“我需要情感安抚能力”，不必关心具体实现。
· Token 预算友好：通过索引-定义-资源三层渐进式加载，确保上下文开销极小。

---

3. 核心概念定义

3.1 Skills（技能）

Skills 是有状态的、多步骤的工作流或专业知识包，通常封装了特定场景下的完整对话策略与话术逻辑。

· 特点：可包含条件分支、用户交互循环、情感评估模板。
· 与人格的关系：人格通过能力域声明激活对应的 Skills 类别。
· 执行方式：注入到 System Prompt 或对话上下文中，由 LLM 解释执行，无需额外沙盒。

示例：

· emotional_comfort：安抚情绪，包含共情话术、渐进引导、呼吸练习建议。
· bedtime_story：睡前故事生成，包含故事风格选择、节奏控制、儿童模式等子流程。
· proactive_checkin：主动关心模板，根据时间、历史情绪生成关怀话语。

3.2 Tools（工具）

Tools 是无状态的、单一功能的函数调用接口，用于连接外部世界或执行确定性操作。

· 特点：定义严格的输入/输出 Schema，通过 function calling 机制由 LLM 决定调用。
· 执行方式：在沙盒环境中实际运行，返回结构化结果。
· 权限级别：分为 readonly、user_data、system 三级。

示例：

· get_weather：查询实时天气。
· set_reminder：创建系统提醒。
· search_knowledge_base：检索外部知识库。
· generate_image：调用图像生成 API。

3.3 能力域

能力域是一组语义标签，用于将 Skills/Tools 归类，使人格配置中的 capability_domains 能够直接筛选可用的能力集。

预定义能力域：

域 说明
emotional_care 情绪安抚、共情、心理支持
daily_chat 日常闲聊、天气、新闻
creative_storytelling 故事生成、角色扮演、文字游戏
task_management 提醒、日程、清单
knowledge_query 联网搜索、知识问答
media_generation 图片、音频、视频生成

---

4. Skills 管理设计

4.1 注册与发现

所有 Skills 通过 configs/Plugins/skills/ 目录下的 YAML 定义文件注册。系统启动时扫描该目录，构建 Skills 元数据索引。

注册文件示例：configs/Plugins/skills/emotional_comfort.yaml

```yaml
skill_id: emotional_comfort
name: "情绪安抚"
version: "1.0.0"
category: emotional_care
capability_tags: ["comfort", "anxiety", "sadness", "anger"]
persona_filters: []  # 空表示所有人格可用
token_cost_estimate: 250
definition_file: "emotional_comfort.def.yaml"  # 相对路径，位于同目录
```

4.2 Skill 定义格式

每个 Skill 的主体为一个 .def.yaml 文件，包含完整的提示词模板和步骤逻辑。

示例：emotional_comfort.def.yaml

```yaml
name: emotional_comfort
description: "当用户表达负面情绪时，提供温柔的共情与安抚，引导其放松。"
prompt_template: |
  [技能激活：情绪安抚]
  你现在启用了情绪安抚模式，请遵循以下原则：
  1. 首先用温暖的语言承认用户的情绪，避免否定或轻视。
  2. 提供共情表述，例如：“我能感受到你现在很难过，没关系，我会陪着你。”
  3. 如果用户愿意继续倾诉，用开放式问题引导；如果用户不想说话，安静陪伴。
  4. 可以适时提议一些简单的放松活动（如深呼吸、喝杯水），但不要强求。
  5. 始终保持耐心，语调柔和，使用适度的表情符号（如💕、🥺）。
steps:
  - acknowledge: true
  - empathize: true
  - guide_gently: optional
  - offer_distraction: after_3_turns
```

系统将 prompt_template 注入到 LLM 的 System Prompt 中，实现 Skill 的“软加载”。对于复杂 Skill，可附带额外的资源文件（如图片、音效），在阶段三加载。

4.3 Skills 的生命周期

1. 注册：系统启动，读取 YAML → 建立内存索引。
2. 匹配：决策引擎根据意图和能力域，从索引中选择 1-2 个 Skill。
3. 注入：加载 Skill 的完整 prompt_template 注入上下文。
4. 激活：LLM 根据提示词生成符合该 Skill 风格的回应。
5. 停用：当对话进入其他意图域，系统自动移除旧的 Skill 提示。

---

5. Tools 管理设计

5.1 注册与 Schema 定义

Tools 同样通过 configs/Plugins/tools/ 注册。每个 Tool 必须提供符合 OpenAI Function Calling 格式的 JSON Schema。

注册文件示例：configs/Plugins/tools/get_weather.yaml

```yaml
tool_id: get_weather
name: "天气查询"
version: "1.0.0"
category: daily_chat
permission_level: readonly  # readonly | user_data | system
schema_file: "get_weather.schema.json"
executor:
  type: docker  # docker | wasm | local_thread
  image: "yuanbot/tool-weather:latest"  # 若为docker
  timeout: 10s
```

Schema 文件：get_weather.schema.json

```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "获取指定城市的实时天气信息",
    "parameters": {
      "type": "object",
      "properties": {
        "city": {
          "type": "string",
          "description": "城市名称，如 '北京'"
        },
        "lang": {
          "type": "string",
          "enum": ["zh", "en"],
          "default": "zh"
        }
      },
      "required": ["city"]
    }
  }
}
```

5.2 工具执行接口

每个 Tool 必须实现统一的执行入口，无论其内部是调用 API、运行脚本还是查询数据库。

执行请求格式（通过 gRPC 发送给沙盒）：

```protobuf
message ToolExecutionRequest {
  string tool_id = 1;
  string invocation_id = 2;  // 唯一调用 ID
  map<string, string> params = 3;
  string auth_token = 4;      // 受限权限令牌
}
```

执行响应：

```protobuf
message ToolExecutionResponse {
  string invocation_id = 1;
  bool success = 2;
  string result_json = 3;      // 结构化结果
  optional string error = 4;
}
```

5.3 Tools 的调用流程

1. LLM 在响应中生成 tool_calls。
2. 能力调用编排器解析调用请求，从 Tools Pool 获取 Tool 定义。
3. 进行安全策略检查（权限是否满足，沙盒是否可用）。
4. 将请求发送至执行沙盒管理器，沙盒执行并返回结果。
5. 编排器将结果以 tool role 的消息格式追加到对话历史。
6. 决策引擎决定是否继续调用工具或生成最终回复。

---

6. 三层渐进式动态加载

为解决大量工具定义消耗 Token 的问题，本系统采用严格的加载深度控制。

6.1 阶段一：启动时——元数据索引

· 内容：所有已启用 Skill/Tool 的 id、name、capability_tags、token_cost_estimate。
· 存储：内存中的 Radix/Trie 树，按能力域索引。
· Token 成本：不进入 LLM 上下文，仅占服务器内存。
· 目的：快速检索，不占用宝贵的上下文窗口。

6.2 阶段二：匹配时——定义注入

· 触发条件：决策引擎根据当前意图、人设能力域、历史工具偏好，选择 1~2 个 Skill 和最多 3 个 Tool。
· 注入内容：
  · Skill：完整的 prompt_template（约 200-500 tokens）。
  · Tool：标准 Function Calling Schema（约 100-300 tokens/tool）。
· 实现：动态加载器从文件或缓存中读取完整定义，注入到本次的 System Prompt 或 function definitions 中。

6.3 阶段三：执行时——资源获取

· 触发条件：Tool 执行过程中需要的额外数据（如大型 API 文档、示例库、多语言文件）。
· 加载方式：通过 LRU 缓存按需获取，不常驻内存。
· Token 成本：这些资源不直接进入 LLM 上下文，而是作为 Tool 执行环境内部的参考，或仅在 LLM 需要错误处理时选择性注入。

整体效果：即使系统安装了上百个 Skills/Tools，每个会话初始只增加约 50 tokens 的索引开销，注入定义后仅增加 500-1500 tokens，与直接平铺所有定义相比节省 95% 以上。

---

7. 安全沙盒执行架构

安全沙盒确保 Tool 的执行不会威胁主机系统或用户隐私。

7.1 沙盒类型

类型 隔离级别 适用场景
Docker 容器 强 调用外部 API、运行第三方代码
WASM 沙盒 中 轻量计算、数据格式转换
本地受限线程 低（权限限制） 内置函数（如数学计算），无需网络

7.2 通信与权限模型

所有 Tool 执行请求通过 gRPC 发送到沙盒管理器。每个调用携带一个作用域受限的 JWT 权限令牌，令牌中声明：

· 调用者身份（哪个用户、哪个会话）
· 允许访问的资源范围（如只读文件系统、特定网络域名）
· 有效期（通常 60 秒）

沙盒内部的服务在收到请求后验证令牌，拒绝越权操作。

7.3 权限级别

· readonly：无状态，无副作用（如天气查询、知识检索）。默认允许。
· user_data：可访问/修改用户个人数据（如设置提醒、更新偏好）。需用户显式确认首次使用。
· system：可管理系统资源（如安装插件、修改配置）。仅限管理员角色，且需二次认证。

7.4 执行超时与资源限制

每个 Tool 配置最大执行时长（默认 10 秒），超时则沙盒强制终止并返回超时错误。Docker 容器还限制 CPU 和内存使用。

---

8. 能力域匹配与决策流程

决策系统通过能力调用编排器与能力系统交互，核心流程：

1. 决策引擎输出 GenerationDirective，其中包含 selected_skills 和 candidate_tools。
2. 编排器调用 CapabilityAPI.load_for_intent(domain, persona_filters)，获取匹配的 Skill 和 Tool 定义。
3. 编排器将 Skill 定义传递给上下文组装器注入，Tool 的 Schema 注入到 LLM function calling 参数。
4. LLM 返回后，若包含 tool call，编排器转发给 CapabilityAPI.execute_tool()。
5. 执行结果传回对话，循环直至无 tool call 或达到最大轮次。

人格过滤：Skills 的注册文件中可设置 persona_filters，例如“毒舌型”人格的 emotional_comfort 可能被替换为略带嘲讽的安慰 Skill，确保角色一致性。

---

9. 配置管理

9.1 目录结构

```
configs/
└── Plugins/
    ├── skills/
    │   ├── emotional_comfort.yaml
    │   ├── emotional_comfort.def.yaml
    │   ├── bedtime_story.yaml
    │   ├── bedtime_story.def.yaml
    │   └── ...
    └── tools/
        ├── get_weather.yaml
        ├── get_weather.schema.json
        ├── set_reminder.yaml
        ├── set_reminder.schema.json
        └── ...
```

9.2 技能/工具的启用与禁用

每个注册文件中有 enabled 字段（默认 true），设为 false 则不会加载。动态调整无需重启。

9.3 全局配置

configs/bot.yaml 中可配置：

```yaml
capabilities:
  loading_strategy: "progressive"  # progressive | full
  max_tools_per_turn: 3
  tool_execution_timeout: 10
  sandbox:
    default_type: docker
    wasm_runtime: wasmtime
```

---

10. 社区开发标准

基于 Y.E.S. 规范，社区贡献 Skills/Tools 需遵循：

10.1 Skill 扩展包结构

```
yuanbot-skill-emotional_comfort/
├── manifest.json
├── definition.yaml       # 技能定义
├── resources/            # 可选：提示词变体、多语言文件
│   └── prompts_zh.txt
├── README.md
└── test_skill.py
```

manifest.json 示例：

```json
{
  "type": "skill",
  "id": "emotional_comfort",
  "name": "情绪安抚",
  "version": "1.0.0",
  "author": "community",
  "category": "emotional_care",
  "capability_tags": ["comfort", "anxiety"],
  "persona_filters": [],
  "dependencies": []
}
```

10.2 Tool 扩展包结构

```
yuanbot-tool-get_weather/
├── manifest.json
├── schema.json           # Function Calling Schema
├── executor.py           # 若为 local_thread 类型
├── Dockerfile            # 若为 docker 类型
├── requirements.txt
├── README.md
└── test_tool.py
```

10.3 提交与上架

开发者通过 yuanbot-cli create --type tool/skill 生成脚手架，实现后提交 PR，经过 CI 接口合规检查和社区审核，合并后出现在扩展市场。

---

11. 与外部系统的接口

11.1 与人格与行为决策系统

· 输入：GenerationDirective（包含意图、人格域、候选技能/工具列表）。
· 输出：LoadedCapabilities（包含可注入的 Skill 提示、Tool 定义）。
· 工具结果反馈：ToolExecutionResult 返回给决策引擎，附加到对话历史。

11.2 与 AI 提供商适配系统

· Tools 的 Schema 被格式化为符合所选 LLM 的 function calling 格式，通过适配器接口传入。

11.3 与记忆系统

· Tool 执行结果可选择性地存储为情景记忆（如“用户查询了北京天气”），但需经过隐私策略检查。

---

12. 性能与可靠性

· 索引缓存：启动后所有元数据索引常驻内存，匹配耗时 < 1ms。
· 定义缓存：最近使用的 Skill/Tool 定义在内存中缓存，避免反复读取文件。
· 沙盒预热：Docker 沙盒可预先启动少量实例，减少冷启动延迟。
· 降级：若沙盒环境不可用，标记为 readonly 级别的本地工具仍可通过受限线程执行。

---

13. 扩展性蓝图

未来可能增加：

· Skill 链式组合：多个 Skill 组成流水线（如安抚→讲笑话）。
· Tool 学习：基于频繁调用参数自动优化 Schema。
· 多模态 Tools：直接返回图片、音频，而非仅 URL。

---

本详细设计定义了缘·Bot 的能力扩展体系，使其在保持“温柔灵魂”的同时，也能灵活、安全地调用各种现代化工具，实现了陪伴与实用的完美平衡。