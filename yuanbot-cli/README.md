# yuanbot-cli

> YuanBot 安装引导工具 — 一行命令部署完整的 [YuanBot](https://github.com/Grabrun/YuanBot) AI 虚拟伴侣。

```bash
pip install yuanbot-cli
yuanbot install
```

## 这是什么

`yuanbot-cli` 是一个**轻量级安装器**，只有一个任务：帮你把完整的 YuanBot 部署到本地。

你只需要安装这一个 100KB 的小包，然后 `yuanbot install` 就会自动完成剩下的所有事情：

1. ✅ 检查 Python 3.12+ 环境
2. ✅ 从 GitHub 克隆最新代码
3. ✅ 创建虚拟环境
4. ✅ 安装 YuanBot 及其依赖
5. ✅ 生成初始配置
6. ✅ 交互式配置 AI 提供商和 API Key
7. ✅ 运行系统诊断验证
8. ✅ 打印下一步指引

## 快速开始

```bash
# 1. 安装
pip install yuanbot-cli

# 2. 全自动安装 YuanBot
yuanbot install

# 3. 根据提示选择 AI 提供商并输入 API Key

# 4. 安装完成后
cd YuanBot
source .venv/bin/activate
yuanbot start
```

## 非交互式安装

适合 Docker 和自动化脚本：

```bash
pip install yuanbot-cli
yuanbot install \
  --provider deepseek \
  --api-key "sk-..." \
  --non-interactive
```

## 指定安装目录

```bash
yuanbot install --dir /opt/yuanbot
```

## 工作原理

```
yuanbot install
    │
    ├── git clone https://github.com/Grabrun/YuanBot.git
    ├── python -m venv .venv
    ├── pip install -e .[dev]      ← 这里安装完整的 yuanbot 包
    ├── yuanbot config init
    ├── 配置 AI 提供商 + API Key
    └── yuanbot doctor             ← 验证安装
```

安装完成后，完整的 `yuanbot` 命令（包含 start/tui/webui/doctor 等所有功能）会在虚拟环境中可用。

## 与完整 yuanbot 包的关系

| | yuanbot-cli | yuanbot (完整版) |
|---|---|---|
| 大小 | ~100KB | ~10MB (含依赖) |
| 安装方式 | `pip install yuanbot-cli` | 由 `yuanbot install` 自动安装 |
| 命令 | `install`, `version` | `start`, `tui`, `doctor`, `config`, `provider`, `persona`, ... |
| 用途 | 安装引导 | 日常使用 |

## 发布到 PyPI

```bash
pip install build twine
cd yuanbot-cli
python -m build
twine upload dist/*
```

## License

MIT
