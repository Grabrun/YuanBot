# Installation Guide

> **Recommended**: Virtual environment + `uv` for speed and isolation.

## Requirements

| Item | Requirement |
|------|-------------|
| Python | **3.12 or 3.13** |
| OS | Linux / macOS / Windows |
| Git | For source clone & auto-update |
| RAM | ≥ 2GB (≥ 8GB for local models) |
| AI API Key | At least one provider (DeepSeek / OpenAI / Claude) |

---

## Option 1: Source Install (Recommended)

YuanBot requires **source installation** for the full config directory and optional extras.

### 1. Clone

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
```

### 2. Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
```

### 3. Install core

```bash
pip install -e .
```

Verify:
```bash
yuanbot version
# → yuanbot v1.2.2
```

### 4. Install extras

| Extra | Description | Command |
|-------|-------------|---------|
| `cli` | TUI + rich output | `pip install -e ".[cli]"` |
| `openai` | OpenAI GPT models | `pip install -e ".[openai]"` |
| `anthropic` | Anthropic Claude | `pip install -e ".[anthropic]"` |
| `tts` | Speech synthesis | `pip install -e ".[tts]"` |
| `wechat` | WeChat iLink channel | `pip install -e ".[wechat]"` |
| `discord` | Discord bot | `pip install -e ".[discord]"` |
| `mysql` | MySQL support | `pip install -e ".[mysql]"` |
| `redis` | Redis cache/queue | `pip install -e ".[redis]"` |
| `milvus` | Milvus vector DB | `pip install -e ".[milvus]"` |
| `graph` | Graph DB (Kuzu/Neo4j) | `pip install -e ".[graph]"` |
| `onnx` | Local ONNX intent model | `pip install -e ".[onnx]"` |
| `all` | Everything | `pip install -e ".[all]"` |

```bash
# Common combo: CLI + OpenAI + Claude
pip install -e ".[cli,openai,anthropic]"
```

---

## Option 2: yuanbot-cli (New Users)

```bash
pip install yuanbot-cli
yuanbot install
```

The CLI will guide you through: cloning, venv creation, AI provider config, and channel setup.

---

## Option 3: Docker

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
cp .env.example .env
# Edit .env with your API keys
docker-compose up -d
```

> ⚠️ Docker mode does **not** support TUI or some channel adapters.

---

## Verify

```bash
yuanbot version
yuanbot doctor   # system diagnostics
yuanbot start    # start server
yuanbot tui      # TUI (requires cli extra)
```

---

## Troubleshooting

### Q: "gbk codec can't decode byte" on Windows

**Cause**: YAML files contain Chinese text; Windows default GBK encoding.
**Fix**: Upgrade to v1.2.2+ which forces UTF-8 on all YAML reads.

### Q: "No module named 'rich'"

**Cause**: TUI requires the `cli` extra.
**Fix**: `pip install -e ".[cli]"`

### Q: How to update?

```bash
git pull
source .venv/bin/activate
pip install -e . --upgrade
# Or: yuanbot update
```
