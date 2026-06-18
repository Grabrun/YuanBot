# 快速开始指南

5 分钟内运行你的第一个 AI 虚拟伴侣 🤖

---

## 1. 安装

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
pip install -e ".[cli,openai]"
```

> 详见 [安装指南](/guide/installation) 获得更多安装方式。

## 2. 配置 AI 提供商

```bash
yuanbot install
```

按提示选择 AI 提供商并填入 API Key。  
或手动编辑 `configs/Providers/` 下对应的 yaml 文件。

## 3. 启动服务

```bash
yuanbot start
```

看到 `🌸 YuanBot 启动完成` 表示服务运行中。

## 4. 打开 Web 聊天界面

在浏览器打开 http://localhost:8000

即可通过 Web 界面与你的 AI 伴侣对话。

## 5. 配置消息通道（可选）

### NapCat QQ

1. 修改 `configs/Channels/napcat.yaml`：
```yaml
enabled: true
config:
  reverse_ws_host: "0.0.0.0"
  reverse_ws_port: 8080
  http_host: "127.0.0.1"
  http_port: 3000
```

2. 在 NapCat 的 `onebot_config.json` 中添加反向 WS：
```json
{
  "ws_reverse_servers": [{
    "name": "yuanbot",
    "url": "ws://你的IP:8080/onebot/v11/ws"
  }]
}
```

3. 重启 YuanBot

### 微信（iLink）

1. 修改 `configs/Channels/wechat.yaml`，`enabled: true`
2. 重启 YuanBot，终端会显示登录二维码
3. 微信扫码登录

## 6. 支持的命令

| 命令 | 用途 |
|------|------|
| `yuanbot start` | 启动 HTTP 服务 |
| `yuanbot tui` | 启动终端聊天界面 |
| `yuanbot install` | 交互式安装引导 |
| `yuanbot doctor` | 系统诊断 |
| `yuanbot update` | 更新到最新版 |
| `yuanbot version` | 显示版本号 |

## 下一步

- 📖 阅读 [配置指南](/guide/configuration) 了解全部配置选项
- 🧩 安装 [Skills 和 Tools](/guide/customization) 扩展能力
- 🏗️ 查看 [系统架构](/guide/design/architecture-v1.5) 理解设计理念
