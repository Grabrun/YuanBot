# インストールガイド

> **推奨**: 仮想環境 + `uv` を使用すると、分離された高速な環境が構築できます。

## 必要条件

| 項目 | 要件 |
|------|------|
| Python | **3.12 または 3.13** |
| OS | Linux / macOS / Windows |
| Git | ソースコードのクローンと自動更新用 |
| RAM | ≥ 2GB（ローカルモデル使用時 ≥ 8GB） |
| AI API Key | 最低1つのプロバイダーが必要（DeepSeek / OpenAI / Claude） |

---

## 方法1：ソースインストール（推奨）

### 1. クローン

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
```

### 2. 仮想環境を作成

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
```

### 3. コアをインストール

```bash
pip install -e "."
```

### 4. 拡張機能をインストール

```bash
# CLI + OpenAI + Claude
pip install -e ".[cli,openai,anthropic]"
# 全機能
pip install -e ".[all]"
```

---

## 方法2：yuanbot-cli（初心者向け）

```bash
pip install yuanbot-cli
yuanbot install
```

---

## 方法3：Docker

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
cp .env.example .env
# .env を編集して API Key を入力
docker-compose up -d
```

---

## 確認

```bash
yuanbot version
yuanbot start
yuanbot tui
```
