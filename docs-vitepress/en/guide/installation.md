# Installation

> 🚧 **This page is a work in progress.** English documentation is being translated.

## Requirements

- Python 3.12+
- git
- pip / uv
- Docker (optional)

## via source (recommended)

::: code-group

```bash [Linux / macOS]
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
yuanbot version
```

```powershell [Windows]
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
python -m venv .venv
.venv\Scripts\activate
pip install -e ".\[dev]"
yuanbot version
```

:::

## via Docker

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
cp .env.example .env
docker-compose up -d
```

---

*English translation coming soon. 🌸*
