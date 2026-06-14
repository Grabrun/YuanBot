# インストール

> 🚧 **このページは準備中です。**

## 必要条件

- Python 3.12+
- pip / uv
- Docker（オプション）

## ソースコードインストール（推奨）

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

## Docker デプロイ

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
cp .env.example .env
docker-compose up -d
```

---

*日本語翻訳は準備中です。🌸*
