---
layout: home

hero:
  name: "🌸 YuanBot"
  text: "道具ではなく、伴走"
  tagline: 記憶と感情を持ち、自ら寄り添うオープンソースAIバーチャルコンパニオン
  actions:
    - theme: brand
      text: はじめる
      link: /ja/guide/getting-started
    - theme: alt
      text: GitHub
      link: https://github.com/Grabrun/YuanBot

features:
  - icon: 🧠
    title: 4層メモリモデル
    details: ワーキングメモリ · ファクトメモリ · エピソードメモリ · セマンティックメモリ
  - icon: 💖
    title: 感情認識エンジン
    details: リアルタイムの感情分析で最適な応答を提供
  - icon: 🌅
    title: プロアクティブな伴走
    details: ユーザーが話しかけるのを待たず、自ら寄り添う
  - icon: 🔄
    title: マルチペルソナ
    details: シナリオに応じてカスタマイズ可能な性格
  - icon: 🔌
    title: マルチプラットフォーム
    details: WeChat、QQ、Telegram、Discordなど8チャンネル対応
  - icon: 🤖
    title: 8つのAIプロバイダー
    details: OpenAI、DeepSeek、Claude、GLM、Qwenなど
---

> 🚧 **日本語ドキュメントは準備中です。**  
> 現在翻訳を進めています。当面は[中国語ドキュメント](/)をご参照ください。

## クイックインストール

### pip

```bash
# 源码安装（詳しくはインストールガイドを参照）
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
yuanbot start
```

### Docker

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
cp .env.example .env
docker-compose up -d
```

---

> **© 2026 YuanBot** · Made with 🌸 by [Grabrun](https://github.com/Grabrun)
