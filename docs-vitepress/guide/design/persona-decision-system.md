---
title: 人格与行为决策系统
description: YuanBot 人格与行为决策系统 v1.4 详细设计
---

🌸 缘·Bot 人格与行为决策系统详细设计文档 (v1.4)

版本历史

| 版本 | 日期 | 修改内容 |
|------|------|----------|
| v1.0 | 2026-05-17 | 初始详细设计，基于总体架构 v1.4 |
---

1. 系统定位与目标

人格与行为决策系统是 缘·Bot 的“大脑与灵魂”，是所有交互行为的最高决策中枢。它并非简单地调用大语言模型，而是基于 角色人设、长期记忆、当前情感状态和对话上下文 进行综合推理，最终决定“说什么、用什么语气说、调用什么能力”。

核心目标：

· 人格一致性：严格遵循设定的人格配置，确保交互风格、情绪表达和价值倾向的长期稳定。
· 情境感知决策：能根据记忆系统提供的用户画像、历史情景，动态调整回应策略。
· 智能能力编排：根据当前意图和决策结果，自动选择并注入合适的 Skills 与 Tools，实现能力按需使用。
· 高效资源利用：通过上下文组装和 Token 预算管理，在有限的上下文窗口内最大化推理质量。

---

2. 系统架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│                  人格与行为决策系统 (Orchestrator)                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │ 意图识别  │  │ 情感分析  │  │ 记忆检索  │  │ 人设加载  │         │
│  │ Intent   │  │ Emotion  │  │ Memory   │  │ Persona  │         │
│  │ Engine   │  │ Engine   │  │ Retriever│  │ Loader   │         │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘         │
│       └──────────────┼──────────────┼──────────────┘              │
│                      ▼              ▼                              │
│               ┌──────────────────────────┐                        │
│               │      对话决策引擎         │                        │
│               │   Dialogue Decision      │                        │
│               │        Engine            │                        │
│               └──────────┬───────────────┘                        │
│                          │                                        │
│          ┌───────────────┼───────────────┐                        │
│          ▼               ▼               ▼                        │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐                │
│  │ 上下文    │  │ Token 预算   │  │ 能力调用      │                │
│  │ 组装器   │  │ 管理器       │  │ 编排器        │                │
│  │ Context  │  │ Token Budget │  │ Capability   │                │
│  │ Builder  │  │ Manager      │  │ Orchestrator │                │
│  └──────────┘  └──────────────┘  └──────────────┘                │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │         统一决策接口 (Decision API)                       │    │
│  │  decide(UserMessage) → DecisionResult                     │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

决策引擎是中心枢纽，它接收来自意图识别、情感分析、记忆检索和人设加载的结果，综合判断后指挥上下文组装器构建最终 Prompt，并授权能力调用编排器加载所需 Skills/Tools，最后通过 AI 提供商适配系统获取模型生成结果。

---

3. 核心模块设计

3.1 意图识别引擎

职责：识别用户输入的核心意图，为后续决策和能力选择提供基础分类。

· 输入：标准化 UserMessage 的文本内容。
· 输出：意图分类标签及置信度，例如：
  ```json
  {
    "primary": "emotional_seeking_comfort",
    "secondary": ["casual_chat"],
    "confidence": 0.92,
    "entities": {"topic": "work_stress"}
  }
  ```
· 实现方式：
  · 规则优先：对于明确的命令式意图（如 /set_reminder），直接匹配规则，零延迟。
  · 轻量模型辅助：使用本地小模型（如 bert-base-uncased 微调）或当前活跃 LLM 自身进行意图分类，在无命令时触发。
· 与能力域映射：意图标签与角色人设中的 capability_domains 关联，如 emotional_seeking_comfort 映射到 emotional_care 域。

3.2 情感分析引擎

职责：分析用户消息和当前会话历史中的情感色彩，提供情绪维度数据。

· 输入：用户消息文本 + 最近 N 轮对话摘要。
· 输出：情感分析结果，包括情绪类别、强度、紧急度等：
  ```json
  {
    "emotion": "anxiety",
    "intensity": 0.78,
    "valence": "negative",
    "arousal": "high",
    "needs_immediate_comfort": true
  }
  ```
· 双模式运行：
  · 轻量级：基于 VAD (Valence-Arousal-Dominance) 词典或本地情感模型，在无 GPU 环境快速响应。
  · 深度分析：调用 AI 提供商进行链式思考分析，提取更细腻的情绪线索（如“表面平静但深层焦虑”）。
· 历史趋势：结合记忆系统提供的情感轨迹，判断用户当前情绪是突发还是长期趋势。

3.3 记忆检索协调器

职责：协调记忆系统，为当前对话提供最相关的情境和事实。

· 它并非直接实现记忆检索，而是作为决策引擎与记忆系统之间的适配层。
· 发送请求：根据意图和实体，向记忆系统发起“情景触发式检索”和“事实记忆查询”。
· 接收结果：获取历史情景摘要、相关事实记忆、用户画像快照，并格式化为 MemoryContext 对象。
· 记忆上下文结构：
  ```python
  @dataclass
  class MemoryContext:
      episodic_nodes: List[dict]  # 匹配到的情景节点
      facts: dict                 # 相关事实记忆，如 {"birthday": "1995-03-21", "hates": "cilantro"}
      persona_snapshot: dict      # 当前角色人设摘要
      relationship_stage: str     # 关系阶段，如 "intimate"
      trust_score: float          # 信任度
  ```

3.4 人设加载器

职责：加载并维护当前活跃的 AI 角色人设配置。

· 配置来源：configs/persona.yaml 或社区下载的角色包。
· 人设配置结构：
  ```yaml
  persona_id: gentle_companion
  name: "小缘"
  description: "温柔细腻的陪伴型AI女友"
  voice_style:
    tone: "warm"
    speech_pattern: "soft_and_caring"
    vocabulary_level: "simple_and_intimate"
  behavior_rules:
    - "永远不评判用户的感受"
    - "当用户情绪低落时优先安抚，而非给出解决方案"
    - "主动分享日常小确幸，但不过度"
  capability_domains:
    - emotional_care
    - daily_chat
    - creative_storytelling
  emotional_profile:
    baseline_mood: "cheerful"
    empathy_level: 0.9
  ```
· 动态调整：根据记忆系统中的 relationship_stage 自动调整某些参数（如亲密度提高后可以使用更亲昵的称呼）。

3.5 对话决策引擎 (核心中枢)

职责：整合上述所有信号，做出高级行为决策。

决策流程：

1. 输入融合：接收 UserMessage、IntentResult、EmotionResult、MemoryContext、PersonaProfile。
2. 策略选择：基于当前状态选择响应策略：
   · COMFORT_FIRST：用户情绪强烈负面且需要安慰。
   · CASUAL_CHAT：日常闲聊。
   · TASK_ORIENTED：明确的任务指令。
   · PROACTIVE_FOLLOWUP：由主动系统触发，需要自然切入话题。
   · MEMORY_REFLECTION：用户触发回忆，需要深度检索记忆。
3. 能力决策：根据策略和意图，选择需要注入的 Skills 和可能调用的 Tools。
   · 例如策略为 COMFORT_FIRST，则选中 emotional_comfort_skill，并可能准备工具 play_music。
4. 生成指令：输出一个 GenerationDirective 对象，指导上下文组装器和能力编排器工作：
   ```python
   @dataclass
   class GenerationDirective:
       strategy: str
       persona_profile: dict
       memory_context: MemoryContext
       intent: IntentResult
       emotion: EmotionResult
       selected_skills: List[str]       # 需要注入的 Skills ID
       candidate_tools: List[str]       # 可能使用的工具ID（用于工具定义注入）
       suggested_temperature: float
       max_response_length: int
   ```

3.6 上下文组装器

职责：根据决策指令，拼装最终发送给 LLM 的完整 Prompt。

· 组装流程：
  1. 系统级提示：从人设配置生成核心 System Prompt，包含角色描述、行为规则、语音风格。
  2. 记忆注入：将 MemoryContext 中的情景节点和事实记忆格式化为 [记忆提示] 区块，注入到 System Prompt 之后。
  3. 工具定义注入：从能力系统获取 candidate_tools 的完整定义，以符合 LLM function calling 格式注入到上下文中。
  4. 历史对话：插入当前会话的工作记忆（最近 N 轮对话）。
  5. 当前用户消息：附加最新的 UserMessage。
· Token 预算控制：组装过程中实时计算 Token 数，若超出限制则按优先级裁剪：先缩减历史对话轮次，再精简低相关性记忆，最后减少备选工具定义。

3.7 Token 预算管理器

职责：动态管理每个会话的上下文窗口，确保不超出模型限制。

· 预算分配：
  · 系统提示：~500 tokens
  · 记忆提示：~300-800 tokens
  · Skills 定义：~200-500 tokens/skill
  · Tools 定义：~100-300 tokens/tool
  · 历史对话：窗口剩余全部，但至少保留最近 3 轮
  · 模型响应预留：~500 tokens
· 动态调整：当组装内容超出预算时，按策略降级：
  1. 压缩记忆：将详细记忆摘要浓缩为关键词。
  2. 减少工具：只保留最可能使用的 1-2 个工具。
  3. 压缩历史：淘汰较早的对话轮次，并对保留的历史做摘要。

3.8 能力调用编排器

职责：管理 Skills 的动态加载和 Tools 的实际调用。

· Skills 注入：根据决策引擎选定的 Skills ID，从能力系统获取完整 Skill 定义，交由上下文组装器注入。
· Tools 调用循环：
  1. 当 LLM 响应中携带 tool_calls 时，编排器向能力系统请求执行。
  2. 能力系统在沙盒中执行，返回结果。
  3. 编排器将结果附加到对话历史，并重新进入决策流程，决定是否继续调用工具或生成最终回复。
· 安全策略检查：在工具执行前，检查当前人设是否具有调用该工具的权限。

---

4. 配置管理

4.1 角色人设配置

角色人设配置文件统一存放在 configs/Personas/ 目录，支持多角色并存，运行时通过 bot.yaml 中的 active_persona 指定当前人格。

目录结构：

```
configs/
└── Personas/
    ├── gentle_companion.yaml
    └── lively_friend.yaml
```

示例 gentle_companion.yaml：

```yaml
persona_id: gentle_companion
name: "小缘"
version: "1.0.0"
description: "温柔体贴的长期伴侣"
voice_style:
  tone: "warm"
  speech_pattern: "gentle_and_caring"
  emoji_usage: "occasional_soft"
behavior_rules:
  - "用户倾诉时，先共情再引导"
  - "不主动结束对话"
capability_domains:
  - emotional_care
  - daily_chat
  - storytelling
emotional_profile:
  baseline_mood: "calm_affectionate"
  empathy: 0.95
```

4.2 决策引擎参数

在 configs/bot.yaml 中可对决策引擎行为进行全局调优：

```yaml
orchestrator:
  intent_engine:
    use_local_model: true
    model_name: "yuanbot-intent-v1"
  emotion_engine:
    deep_analysis_threshold: 0.7   # 情绪强度超过此值触发深度分析
  token_budget:
    total_limit: 8000
    memory_ratio: 0.3
    conversation_ratio: 0.5
```

---

5. 与外部系统的交互接口

5.1 与记忆系统交互

· 接口：MemorySystem.retrieve(user_id, query_vector, entities, top_k)
· 调用时机：每次收到用户消息，决策引擎通过记忆检索协调器发起。
· 返回格式：MemoryContext 对象。

5.2 与能力系统交互

· Skills 获取：SkillManager.get_skill(skill_id) -> SkillDefinition
· Tools 获取与执行：ToolManager.get_tool_schema(tool_id), ToolManager.execute(tool_id, params) -> ToolResult

5.3 与 AI 提供商系统交互

· 流式对话：AIProvider.stream_chat(messages, tools, temperature, max_tokens)
· 非流式对话：AIProvider.chat_completion(...)
· 所有模型调用统一通过 AI 提供商适配器的抽象接口进行，不直接依赖特定厂商。

---

6. 决策流水线过程

```
UserMessage
  │
  ├─→ 意图识别引擎 → IntentResult
  ├─→ 情感分析引擎 → EmotionResult
  ├─→ 记忆检索协调器 → MemoryContext
  ├─→ 人设加载器 → PersonaProfile
  │
  └─→ 对话决策引擎 ─── 综合分析 ──→ GenerationDirective
                                          │
                        ┌─────────────────┤
                        ▼                 ▼
                 上下文组装器       能力调用编排器
                        │                 │
                        ├── 组装 Prompt ──┤
                        │                 │
                        └─→ AI提供商 ────┘
                              │
                              ▼
                        LLM 响应
                              │
                    ┌─ 含 tool_calls? ─┐
                    │ 是              │ 否
                    ▼                 ▼
              Tool 执行并循环      最终回复 → 响应给用户
```

---

7. 扩展性设计

7.1 人设社区市场

· 用户可从社区市场下载现成的人格包，解压到 configs/Personas/ 即可启用。
· 开发者可按 Y.E.S. 规范创建新人格包：
  ```
  yuanbot-persona-xxx/
  ├── manifest.json
  ├── persona.yaml          # 人格定义文件
  └── README.md
  ```

7.2 决策引擎插件

· 允许为决策引擎的特定策略注册自定义插件，例如自定义的意图分类器或情感分析器。
· 插件通过 Plugins/decision/ 目录配置，并在 bot.yaml 中声明。

---

8. 性能与可靠性

· 异步处理：所有分析引擎均支持异步并发，以减少延迟。
· 缓存机制：同一用户短时间内连续对话，意图和情感分析结果可缓存，避免重复计算。
· 降级策略：若本地意图/情感模型加载失败，自动切换为基于规则或纯 LLM 推理的降级模式，确保系统可用。

---

本详细设计定义了人格与行为决策系统的内部结构、核心流程和接口规范，确保缘·Bot 的“大脑”能够有条不紊地维系角色灵魂，做出既符合人设又体贴入微的每一次回应。