🌸 缘·Bot 语音合成系统详细设计文档 (v1.5)

版本历史

版本 日期 修改内容
v1.0 2026-05-22 初始详细设计，基于总体架构 v1.5

---

1. 系统定位与目标

语音合成系统（TTS）是 缘·Bot 的“嗓音”，负责将 AI 生成的文本转化为自然、富有情感的语音输出，为用户提供更沉浸、更温暖的陪伴体验。它与用户界面系统无缝协作，在 WebUI、TUI 以及未来可能的语音通话场景中，让 AI 伴侣“开口说话”。

核心目标：

· 多引擎支持：同时支持本地离线引擎（如 Piper、Edge-TTS）和云端高质引擎（如 OpenAI TTS、Azure TTS），用户可根据隐私需求和硬件条件自由切换。
· 人格化语音：AI 角色的人设可绑定特定的语音风格、音色、语速，使声音成为人格形象不可分割的一部分。
· 实时流式合成：支持边生成文本边输出音频，降低首音延迟，提升对话流畅感。
· 智能缓存：对常用短语、问候语、固定话术的音频结果进行缓存，减少重复合成，节省计算资源或 API 调用成本。
· 灵活配置与扩展：提供统一的适配器接口，社区可贡献新的 TTS 引擎适配器；通过配置文件与人格绑定，开箱即用。

---

2. 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                   语音合成系统 (TTS System)                │
├──────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────────────────────────────────────────┐    │
│  │               TTS 管理器 (TTS Manager)             │    │
│  │  · 引擎选择  · 人格语音映射  · 缓存策略  · 流控   │    │
│  └──────────────────────┬───────────────────────────┘    │
│                         │                                  │
│  ┌──────────────────────▼───────────────────────────┐    │
│  │            统一 TTS 适配器接口 (TTSAdapter)         │    │
│  └──┬──────────┬──────────┬──────────┬──────────────┘    │
│     │          │          │          │                     │
│  ┌──▼───┐ ┌───▼──┐ ┌───▼───┐ ┌───▼──────┐               │
│  │Edge- │ │Piper │ │OpenAI │ │Azure     │  ...           │
│  │TTS   │ │TTS   │ │TTS    │ │TTS       │               │
│  └──────┘ └──────┘ └───────┘ └──────────┘               │
│                                                            │
│  ┌──────────────────────────────────────────────────┐    │
│  │              音频缓存层 (Audio Cache)              │    │
│  │  · LRU 内存缓存  · 本地文件缓存  · 键值生成策略    │    │
│  └──────────────────────────────────────────────────┘    │
│                                                            │
└──────────────────────────────────────────────────────────┘
```

· TTS 管理器：对外暴露统一接口，对内根据当前活跃人格及用户配置选择合适的引擎与音色，处理缓存、流式输出及并发控制。
· 适配器接口：抽象不同 TTS 引擎的差异，定义 synthesize（非流式）与 synthesize_stream（流式）方法。
· 音频缓存层：以文本 hash + 引擎 + 音色为 key，存储合成后的音频数据，减少重复调用。

---

3. 核心模块设计

3.1 TTS 管理器

职责：

· 接收文本合成请求，根据当前 AI 角色人设中定义的 tts_voice 以及全局配置选择目标引擎。
· 调用对应适配器的流式或非流式方法，处理异常与降级。
· 管理音频缓存，优先返回已缓存的音频。
· 提供 synthesize（返回完整音频字节）和 synthesize_stream（返回音频块迭代器）两种模式。

流程（非流式）：

1. 接收输入文本、目标引擎（可选）、目标音色（可选）。
2. 若未指定引擎/音色，从全局配置及活跃人格配置中获取默认值。
3. 以 {engine}:{voice}:{text_hash} 为键查询缓存。
4. 命中 → 直接返回缓存音频。
5. 未命中 → 调用适配器合成 → 写入缓存 → 返回音频。

流程（流式）：

1. 文本传入，可能同时接收来自 LLM 的流式文本块。
2. 管理器维护一个文本缓冲区，当积累到足够长度（如一个句子或标点处）时触发合成。
3. 调用适配器流式合成，边获取音频块边向上游（WebSocket / 播放器）推送。
4. 流式结果不写入缓存（或仅缓存完整合并后的结果），以避免状态管理复杂性。

3.2 缓存策略

缓存层级 存储位置 容量 淘汰策略 说明
L1 内存缓存 进程内存 100 条 LRU 响应最快，适合高频短文本
L2 文件缓存 data/tts_cache/ 500 MB 基于时间和空间的 LRU 持久化，重启后仍可用，适合较长文本

缓存键生成：sha256(engine + "|" + voice + "|" + text[:200])，截取前 200 字符是为了避免超长文本导致哈希计算过重，同时保证高度相似请求能命中。

缓存预热：系统启动时可预加载人格常用的问候语、主动消息模板到 L1 缓存中。

---

4. 统一适配器接口

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional

class TTSAdapter(ABC):
    """TTS 引擎统一接口"""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: float = 1.0,        # 语速倍率
        pitch: float = 1.0,       # 音调倍率
        format: str = "mp3"
    ) -> bytes:
        """非流式合成，返回完整音频字节"""
        pass

    @abstractmethod
    async def synthesize_stream(
        self,
        text: str,
        voice: str,
        rate: float = 1.0,
        pitch: float = 1.0,
        format: str = "mp3"
    ) -> AsyncIterator[bytes]:
        """流式合成，返回音频字节块异步迭代器"""
        pass

    @abstractmethod
    def list_voices(self) -> List[dict]:
        """返回该引擎支持的音色列表 [{'id': 'voice_id', 'name': '...', 'language': 'zh-CN', 'gender': 'female'}]"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查引擎是否可用（网络连通、本地模型存在等）"""
        pass
```

---

5. 预集成引擎

5.1 Edge-TTS (Microsoft Edge 免费 TTS)

· 适配器类：EdgeTTSAdapter
· 特点：免费，中文自然度高，支持多种角色音色，无需 API Key，使用 edge-tts Python 库。
· 音色示例：zh-CN-XiaoxiaoNeural（女，活泼），zh-CN-YunxiNeural（男，稳重），zh-CN-XiaoyiNeural（女，温柔）。
· 适用场景：个人用户首选，无需任何密钥，网络正常即可。

5.2 Piper TTS（本地离线引擎）

· 适配器类：PiperTTSAdapter
· 特点：完全本地离线，无网络依赖，隐私性强；需提前下载语音模型（200-400 MB）；支持多语言；推理速度快（CPU 即可）。
· 音色示例：zh_CN-huayan-medium（女声），zh_CN-ljspeech-medium（男声）。
· 适用场景：对隐私有极高要求的用户、无网络环境。

5.3 OpenAI TTS

· 适配器类：OpenAITTSAdapter
· 特点：高质量，多音色，支持流式，需要 API Key，按字符计费。使用 OpenAI tts-1 或 tts-1-hd 模型。
· 适用场景：追求最佳音质的用户，已订阅 OpenAI 服务的开发者。

5.4 Azure Cognitive Services Speech

· 适配器类：AzureTTSAdapter
· 特点：微软官方，音色库最丰富，神经语音质量极高，支持 SSML 精细控制，需要 Azure 订阅。
· 适用场景：需要多语言、多风格精细控制的商业部署。

---

6. 人格语音绑定

在人格配置文件 (persona.yaml) 中增加 voice 段落：

```yaml
persona_id: gentle_companion
name: "小缘"
voice_style:
  tone: "warm"
  speech_pattern: "gentle_and_caring"
voice:
  engine: "edge-tts"           # 使用的 TTS 引擎 ID
  voice_id: "zh-CN-XiaoxiaoNeural"  # 该引擎下的音色 ID
  rate: 1.0                    # 可选：语速
  pitch: 1.1                   # 可选：音调（略高显得更温柔）
```

· 若人格未配置 voice 字段，则使用全局默认 TTS 设置。
· 支持在对话中动态切换语音（如用命令 /voice piper 临时切换），但不改变人格默认值。

---

7. 配置管理

7.1 全局 TTS 配置

configs/tts.yaml：

```yaml
tts:
  enabled: true
  default_engine: edge-tts     # 默认引擎
  streaming: true              # 是否启用流式合成
  cache:
    memory_size: 100
    file_cache_path: "data/tts_cache"
    file_cache_max_mb: 500
  engines:
    edge-tts:
      enabled: true
    piper:
      enabled: false
      model_dir: "data/piper_models"
    openai:
      enabled: false
      api_key: "${OPENAI_API_KEY}"
      model: "tts-1"
    azure:
      enabled: false
      subscription_key: "${AZURE_SPEECH_KEY}"
      region: "eastus"
```

7.2 引擎选择优先级

1. 用户临时覆盖（如对话命令）。
2. 当前人格的 persona.voice.engine。
3. 全局 tts.default_engine。
4. 第一个可用的引擎。

---

8. 与外部系统的交互

8.1 与人格与行为决策系统

· 决策系统输出文本后，若用户界面请求语音（如 WebUI 点击播放按钮、TUI 开启语音模式），则调用 TTS 管理器生成音频。

8.2 与用户界面系统

· WebUI：通过 REST API 请求单个消息的音频 (GET /api/tts?message_id=xxx)，或通过 WebSocket 接收流式音频块。
· TUI：在终端内通过 ASCII 通知标记或调用外部播放器（如 mpv）播放。

8.3 与接入与通信系统

· 未来若支持语音通道（如电话），TTS 直接向通信系统提供音频流。

---

9. 流式合成与播放同步

流式合成的关键挑战是降低“首字延迟”。设计如下：

1. LLM 通过 WebSocket 推送文本 token。
2. TTS 管理器的 流式缓冲区 收集 token，当检测到句末标点（。！？）、逗号或缓冲区超过阈值（如 20 个字符）时，立即调用适配器的流式合成。
3. 适配器产生的音频块通过同一 WebSocket 连接推送到前端。
4. 前端使用 HTML5 Audio API 或 Media Source Extensions 按顺序播放音频块，实现边生成边播放。

若 TTS 引擎不支持流式合成，则等待完整文本生成后再合成，这会增加延迟，此时前端可先显示文本，再播放音频。

---

10. 性能与优化

· 并行合成：对于不同用户的并发请求，使用异步 I/O 并行调用引擎，充分利用资源。
· 本地引擎预热：Piper 等本地引擎在系统启动时预加载默认音色模型，避免首次调用加载延迟。
· 连接池：对于云端 API，使用 HTTP 连接池复用，减少握手开销。
· 缓存命中率监控：通过系统指标暴露缓存命中率，辅助调优。

---

11. 扩展性

社区可按 Y.E.S. 规范开发新的 TTS 适配器，例如：

· 火山引擎 TTS
· 阿里云 TTS
· 讯飞 TTS

适配器实现 TTSAdapter 接口，并通过 manifest.json 注册，安装后即可在配置中使用。

---

12. 安全与隐私

· 本地引擎优先：鼓励使用 Edge-TTS（免费但需联网，仅文本传输）或 Piper（完全本地），不对用户隐私数据造成额外泄露。
· 云端 API 密钥隔离：通过环境变量注入，日志脱敏，仅活跃引擎的密钥被加载。
· 音频缓存隔离：不同用户的音频缓存文件通过用户 ID 划分目录，防止越权访问（尽管 TTS 通常无用户敏感信息，但为架构一致性考虑）。

---

本详细设计为缘·Bot 赋予了温暖、多变的嗓音，让文字陪伴升级为声情并茂的语音陪伴，同时保持架构的灵活与隐私的尊重。