🌸 缘·Bot 记忆与情感系统详细设计文档 (v1.4)

版本历史

版本 日期 修改内容
v1.0 2026-05-17 初始详细设计，基于总体架构 v1.4

---

1. 系统定位与目标

记忆与情感系统是 缘·Bot 的“海马体与边缘系统”，是整个项目的第一性引擎。它并非被动存储，而是主动构建、维护和演化关于用户的一切认知，是 AI 角色产生“懂你、记住你”体验的根基。

核心目标：

· 长期持续性：跨越会话、跨越时间，持久化用户的偏好、经历、情感轨迹。
· 情境关联：当用户提及某话题时，能自动唤起相关的历史情景，实现“触景生情”般的自然回忆。
· 结构化认知：将零散对话转化为结构化的知识图谱，形成用户画像和关系理解。
· 自主进化：在系统空闲时，自主进行记忆整理、固化、遗忘，模拟人类的记忆强化与衰减。
· 情感感知：不仅存储事实，更存储每段记忆的情感色彩，并分析用户情绪的长期趋势。

---

2. 系统架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│                     记忆与情感系统 (Memory & Emotion System)        │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                   记忆管理核心 (Memory Core)                │   │
│  │                                                             │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │   │
│  │  │ 工作记忆  │  │ 事实记忆  │  │ 情景记忆  │  │ 语义记忆  │  │   │
│  │  │ Working  │  │  Fact    │  │ Episodic │  │ Semantic │  │   │
│  │  │ Memory   │  │  Memory  │  │ Memory   │  │ Memory   │  │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │   │
│  │       └──────────────┼──────────────┼──────────────┘       │   │
│  └──────────────────────┼──────────────┼──────────────────────┘   │
│                         │              │                           │
│  ┌──────────────────────▼──────────────▼──────────────────────┐   │
│  │                    存储引擎抽象层                            │   │
│  │              Storage Engine Abstraction                     │   │
│  └───┬──────────────┬──────────────┬──────────────┬───────────┘   │
│      │              │              │              │                │
│  ┌───▼────┐  ┌──────▼───┐  ┌──────▼───┐  ┌──────▼──────┐        │
│  │ Redis  │  │ SQLite/  │  │ Milvus   │  │ Kuzu/Neo4j │        │
│  │(工作)  │  │ MySQL    │  │ Lite     │  │ (知识图谱)  │        │
│  │        │  │(结构化)  │  │(向量)    │  │            │        │
│  └────────┘  └──────────┘  └──────────┘  └─────────────┘        │
│                                                                    │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                 记忆生命周期管理 (Lifecycle Manager)         │   │
│  │  · 重要性评分  · 遗忘曲线  · 记忆固化  · 冲突解决            │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                 情感状态追踪 (Emotion Tracker)               │   │
│  │  · 会话情感记录  · 长期情绪趋势  · 触发模式分析              │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │            统一记忆 API (Memory API)                         │   │
│  │  · store()  · retrieve()  · update()  · forget()           │   │
│  │  · get_user_profile()  · get_emotion_trend()                │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

设计原则：

· 分层存储：不同特性的记忆使用最适合的存储引擎，而非一刀切。
· 统一入口：外部系统仅通过 Memory API 交互，无需关心底层存储细节。
· 异步固化：记忆的写入尽可能异步，不阻塞对话响应。
· 隐私优先：所有数据自托管，敏感记忆支持加密存储。

---

3. 记忆四层模型详细设计

3.1 工作记忆

定位：当前会话的短期上下文，提供对话连贯性。

存储引擎：Redis，键为 session:{session_id}:working_memory。

数据结构：

```json
{
  "session_id": "sess_abc123",
  "turns": [
    {
      "turn_id": 1,
      "role": "user",
      "content": "今天好累啊",
      "timestamp": 1715900000.0,
      "emotion_analysis": {"emotion": "fatigue", "intensity": 0.6}
    },
    {
      "turn_id": 2,
      "role": "assistant",
      "content": "听起来你今天辛苦了，愿意和我说说发生了什么吗？",
      "timestamp": 1715900002.0
    }
  ],
  "summary": "用户在抱怨疲劳",
  "max_turns": 20
}
```

行为规则：

· 最多保留 20 轮对话（用户+AI 各算一轮），超出则淘汰最旧的。
· 会话结束后，立即触发会话摘要生成，摘要存入情景记忆，原始数据进入临时存档（Redis 中保留 24 小时，供意外断连恢复）。
· 24 小时后 Redis 中的数据自动过期删除。

核心操作：

操作 说明
add_turn() 追加一轮对话，同时更新摘要
get_context() 获取最近 N 轮对话文本
summarize() 生成当前会话的简短摘要
clear() 会话结束，清理并归档

---

3.2 事实记忆

定位：关于用户的结构化事实，长期持久，快速查询。

存储引擎：SQLite（默认）/ MySQL，表名 fact_memories。

数据表结构：

```sql
CREATE TABLE fact_memories (
    id TEXT PRIMARY KEY,                -- UUID
    user_id TEXT NOT NULL,              -- yuanbot_user_id
    category TEXT NOT NULL,             -- 'preference', 'personal_info', 'habit', 'dislike', 'important_date'
    key TEXT NOT NULL,                  -- 如 'favorite_color', 'birthday'
    value TEXT NOT NULL,                -- 如 'blue', '1995-03-21' (以JSON存储复杂值)
    confidence REAL DEFAULT 1.0,        -- 置信度 0.0-1.0
    source TEXT,                        -- 来源：'explicit_statement', 'inferred', 'extracted_from_episodic'
    importance REAL DEFAULT 0.5,        -- 重要性评分
    first_mentioned_at REAL,            -- 首次提及时间戳
    last_updated_at REAL,               -- 最后更新时间戳
    access_count INTEGER DEFAULT 0,     -- 被检索次数
    is_deleted INTEGER DEFAULT 0,       -- 软删除标记
    metadata TEXT DEFAULT '{}'          -- JSON 额外元数据
);

CREATE INDEX idx_fact_user ON fact_memories(user_id);
CREATE INDEX idx_fact_category ON fact_memories(category);
CREATE INDEX idx_fact_key ON fact_memories(user_id, key);
CREATE UNIQUE INDEX idx_fact_unique ON fact_memories(user_id, key) WHERE is_deleted = 0;
```

类别定义：

类别 说明 示例 key
personal_info 个人基本信息 birthday, gender, occupation, location
preference 喜好 favorite_color, favorite_food, music_genre
dislike 厌恶 hates_food, avoids_topics
habit 习惯 morning_routine, sleep_schedule
important_date 重要日期 anniversary, interview_date
relationship 社交关系 pet_name, best_friend
health 健康相关 allergy, medical_condition

置信度机制：

· 用户明确陈述：置信度 = 1.0
· 系统从对话推断：置信度 = 0.6-0.8（需多次确认才提升）
· 置信度低于 0.5 的事实不会被用于决策，仅作为参考。

核心操作：

操作 说明
upsert_fact() 创建或更新事实，自动处理置信度
get_user_facts() 获取用户全部或某类事实
delete_fact() 用户主动删除或系统淘汰
search_facts() 按关键词搜索事实

---

3.3 情景记忆

定位：过往对话的情景摘要，按时间和重要性组织，是“触景生情”的基础。

存储引擎：

· 向量存储：Milvus Lite，存储情景节点的语义向量，用于相似度检索。
· 元数据存储：SQLite/MySQL，存储情景节点的结构化元数据。

Milvus Lite Collection Schema：

```python
{
    "collection_name": "episodic_memories",
    "fields": [
        {"name": "id", "type": DataType.VARCHAR, "max_length": 64, "is_primary": True},
        {"name": "user_id", "type": DataType.VARCHAR, "max_length": 64},
        {"name": "embedding", "type": DataType.FLOAT_VECTOR, "dim": 1536},  # 维度和嵌入模型匹配
        {"name": "timestamp", "type": DataType.INT64},
        {"name": "importance", "type": DataType.FLOAT},
    ],
    "indexes": [
        {"field_name": "embedding", "index_type": "IVF_FLAT", "metric_type": "COSINE"}
    ]
}
```

元数据表结构 (SQLite/MySQL)：

```sql
CREATE TABLE episodic_metadata (
    id TEXT PRIMARY KEY,                -- 与 Milvus 中 ID 一致
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    date TEXT NOT NULL,                 -- '2026-05-17'
    time_of_day TEXT,                   -- 'morning', 'afternoon', 'evening', 'night'
    topic TEXT,                         -- 对话主题
    summary TEXT,                       -- 对话摘要 (200字以内)
    emotional_tone TEXT,                -- 整体情感基调
    emotional_intensity REAL DEFAULT 0.5,
    key_entities TEXT DEFAULT '[]',     -- JSON数组: ["项目截止日", "同事矛盾"]
    user_state TEXT,                    -- 用户当时的状态描述
    ai_response_style TEXT,             -- AI 当时的回应风格
    importance REAL DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    created_at REAL,
    last_accessed_at REAL
);

CREATE INDEX idx_episodic_user ON episodic_metadata(user_id);
CREATE INDEX idx_episodic_date ON episodic_metadata(date);
CREATE INDEX idx_episodic_entities ON episodic_metadata(key_entities);
```

情景触发式检索流程：

```
用户输入: "最近项目压力好大"
         │
         ▼
    ┌─────────────┐
    │  步骤1: 向量化  │  调用 AI 提供商的嵌入模型，获取输入向量
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │  步骤2: 双路径  │
    │  并行检索      │
    ├─────────────┤
    │ 路径A: 语义   │  Milvus Lite 中检索 top_k=5 相似向量
    │ 路径B: 实体   │  SQLite 中搜索 key_entities 包含 "项目" 或 "压力" 的节点
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │  步骤3: 结果合并│  去重后按 (相似度*0.7 + 重要性*0.3) 重新排序
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │  步骤4: 格式化  │  生成 MemoryContext 返回给决策系统
    │  记忆提示      │
    └─────────────┘
```

格式化输出示例：

```
[记忆提示]
你回忆起2026年5月8日的晚上，{user_name}曾和你倾诉过工作上的压力，
当时他提到项目截止日很紧迫，和同事之间有些矛盾。
他当时的心情比较焦虑，你以温柔的方式安抚了他。
现在他再次提到了工作相关的话题，请自然地延续之前的关心。
```

核心操作：

操作 说明
store_episode() 会话结束后存储情景节点（元数据+向量）
retrieve_similar() 情景触发式检索
get_episodes_by_date() 按日期范围查询情景
update_importance() 更新情景节点的重要性评分
merge_episodes() 合并相似度过高的情景节点，避免冗余

---

3.4 语义记忆

定位：从长期交互中提炼的深层认知，形成用户画像和关系理解。这是四层记忆中最抽象但最有价值的层次。

存储引擎：

· 图数据库：Kuzu（嵌入式，默认）/ Neo4j（大规模），存储实体和关系。
· 向量辅助：Milvus Lite 存储实体和关系的语义向量，用于模糊匹配。

图模型设计：

```
节点类型：
  - User: {user_id, name, trust_score, ...}
  - AIPersona: {persona_id, name, ...}
  - Entity: {name, type, ...}  (type: 'person', 'food', 'place', 'activity', 'music', ...)
  - Event: {description, date, emotional_impact, ...}
  - Trait: {name, category, ...}  (category: 'personality', 'emotional_pattern', ...)

关系类型：
  - (:User)-[:LIKES {confidence, first_mentioned}]->(:Entity)
  - (:User)-[:DISLIKES {confidence, reason}]->(:Entity)
  - (:User)-[:HAS_TRAIT]->(:Trait)
  - (:User)-[:EXPERIENCED]->(:Event)
  - (:User)-[:IN_RELATIONSHIP_WITH {stage, since}]->(:AIPersona)
  - (:AIPersona)-[:KNOWS_ABOUT]->(:Entity)  # AI 通过用户了解到的知识
  - (:Entity)-[:ASSOCIATED_WITH {type}]->(:Entity)  # 实体间关联
```

关系阶段模型：

系统根据交互时长、对话深度、信任评分等，自动评估关系阶段：

阶段 指标条件 AI 行为影响
初期 交互天数 < 7 礼貌、保持距离、多倾听
熟悉期 交互天数 7-30, 信任度 > 0.3 可以主动分享、适度调侃
亲密期 交互天数 > 30, 信任度 > 0.6 亲昵称呼、深度共情、主动关心
深度期 交互天数 > 90, 信任度 > 0.8 强烈的情感连接，可以讨论任何话题

信任度计算模型：

```
trust_score = f(
    interaction_days,           # 交互总天数
    interaction_frequency,      # 交互频率
    self_disclosure_depth,      # 用户自我披露的深度
    emotional_vulnerability,    # 用户展示情感脆弱的次数
    consistency_score,          # 用户行为一致性
    negative_event_count      