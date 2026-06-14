# 贡献指南

感谢你对 YuanBot 项目的关注！YuanBot 是一个开放的 AI 虚拟伴侣系统，我们欢迎社区贡献代码、扩展、文档和改进。

## 目录

- [行为准则](#行为准则)
- [快速开始](#快速开始)
- [分支命名规范](#分支命名规范)
- [Commit Message 规范](#commit-message-规范)
- [Pull Request 流程](#pull-request-流程)
- [PR Checklist](#pr-checklist)
- [代码规范](#代码规范)
- [测试规范](#测试规范)
- [扩展开发（Y.E.S. 标准）](#扩展开发yes-标准)
- [文档贡献](#文档贡献)
- [报告问题](#报告问题)

---

## 行为准则

- 尊重所有参与者
- 建设性地提出反馈
- 专注于对社区最有利的事情
- 对他人表示同理心
- 遵循 [Contributor Covenant](https://www.contributor-covenant.org/) 行为准则

---

## 快速开始

### 开发环境

```bash
git clone https://github.com/your-org/yuanbot.git
cd yuanbot
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

或使用推荐工具链：

```bash
pip install uv
uv sync --all-extras
```

### 常用命令

```bash
# 代码检查
uv run ruff check src/ tests/

# 自动修复
uv run ruff check --fix src/ tests/

# 格式化
uv run ruff format src/ tests/

# 运行测试
uv run python -m pytest tests/ -q --tb=short

# 带覆盖率
uv run python -m pytest tests/ --cov=yuanbot --cov-report=term-missing

# 构建
uv build
```

---

## 分支命名规范

| 分支前缀 | 用途 | 示例 |
|----------|------|------|
| `feature/xxx` | 新功能 | `feature/multi-language-support` |
| `fix/xxx` | Bug 修复 | `fix/websocket-timeout` |
| `docs/xxx` | 文档更新 | `docs/api-reference-v2` |
| `refactor/xxx` | 重构 | `refactor/plugin-system` |
| `extension/xxx` | 社区扩展 | `extension/skill-weather-alert` |
| `ext/xxx` | 社区扩展（简写） | `ext/my-tool` |
| `chore/xxx` | 构建/工具变更 | `chore/update-deps` |

---

## Commit Message 规范

采用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
<type>(<scope>): <description>

[optional body]
[optional footer]
```

### 类型

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档 |
| `style` | 代码格式（不影响逻辑） |
| `refactor` | 重构 |
| `perf` | 性能优化 |
| `test` | 测试 |
| `chore` | 构建/工具变更 |
| `ci` | CI 配置变更 |
| `extension` | 扩展相关变更 |

### 示例

```
feat(memory): add semantic memory retrieval by embedding similarity
fix(gateway): handle empty platform_user_id in identity resolution
docs(architecture): update memory system diagram
extension(skill): add emotional comfort skill v1.0
ci: add extension validation workflow for PRs
```

---

## Pull Request 流程

### 标准流程

```
1. Fork 仓库 → 创建分支
         ↓
2. 编写代码 + 测试
         ↓
3. 本地验证（ruff + pytest）
         ↓
4. 提交 PR（填写模板）
         ↓
5. 自动 CI 检查
   ├── Lint & Test & Build
   ├── Extension 验证（如适用）
   └── PR Review 自动评论
         ↓
6. 处理 Review 意见
         ↓
7. 审核通过 → 合并到 main
```

### 扩展 PR 流程

如果是扩展贡献（extension/ 或 ext/ 分支），CI 会额外执行：

1. **manifest.json Schema 验证** — 检查是否符合 Y.E.S. 规范
2. **接口完整性检查** — 验证是否实现了所有必需的抽象方法
3. **安全扫描** — 检测硬编码密钥和常见漏洞模式
4. **依赖审计** — 检查依赖的安全风险
5. **自动标签** — 通过则添加 `extension-ci/pass`，失败则 `extension-ci/fail`

### 审核流程

1. PR 提交后，[PR Review 工作流](.github/workflows/pr-review.yml) 自动评论变更概览和检查清单
2. 自动添加 `needs-review` 标签
3. 项目审核者进行 Code Review
4. 审核通过后添加 `approved` 标签
5. 合并至 main 后，自动触发发布流程

---

## PR Checklist

提交 PR 前，请逐项确认：

### 代码

- [ ] 代码遵循项目规范（ruff check 通过）
- [ ] 类型标注完整（公开函数均有类型标注）
- [ ] 无硬编码密钥或凭证
- [ ] 日志使用 structlog，非 f-string 拼接
- [ ] 无未使用的导入或变量

### 测试

- [ ] 功能变更附带对应测试
- [ ] 所有现有测试依然通过
- [ ] 异步测试使用 `async def test_xxx`
- [ ] 测试覆盖边界情况

### 文档

- [ ] 新增功能更新了对应文档（docs/ 目录）
- [ ] README.md 如有需要已更新
- [ ] CHANGELOG.md 已更新（非 trivial 变更）
- [ ] 如有 API 变更，更新了 API 文档

### 扩展（extension PR 需额外确认）

- [ ] manifest.json 所有必填字段完整
- [ ] manifest.json 类型与代码匹配
- [ ] 实现类继承自正确的基类
- [ ] 必需的接口方法已实现
- [ ] README.md 包含了安装和使用说明
- [ ] 许可证文件已包含

---

## 代码规范

### 风格

- 使用 `ruff` 进行 lint 和格式化
- 行宽 100 字符
- Python 3.12+，积极使用新特性（`type` 语句、`match` 等）
- 导入排序：标准库 → 第三方 → 本地（ruff 自动处理）

```bash
# 检查
ruff check src/ tests/

# 自动修复
ruff check --fix src/ tests/

# 格式化
ruff format src/ tests/
```

### 类型标注

- 所有公开函数必须有类型标注
- 使用 `from __future__ import annotations`
- 优先使用内置类型：`dict` 而非 `Dict`，`list` 而非 `List`
- 可选类型使用 `X | None` 而非 `Optional[X]`

### 日志

使用 `structlog` 进行结构化日志：

```python
import structlog
logger = structlog.get_logger(__name__)

# 好
logger.info("user_created", user_id=user_id, platform=platform)

# 避免
logger.info(f"User {user_id} created on {platform}")
```

### 错误处理

- 使用自定义异常类，而非裸 `raise Exception`
- 异常消息应描述问题原因
- 使用 `try/except` 包裹可能失败的外部调用
- 区分业务异常和系统异常

---

## 测试规范

### 编写测试

- 每个新功能必须附带测试
- 测试文件放在 `tests/` 对应子目录
- 使用 `pytest` + `pytest-asyncio`
- 异步测试使用 `async def test_xxx`

```python
import pytest

class TestMyFeature:
    async def test_basic_case(self, config):
        """测试基本功能"""
        result = await my_function(config)
        assert result.status == "ok"

    async def test_error_handling(self):
        """测试异常处理"""
        with pytest.raises(ValueError, match="invalid"):
            await my_function(invalid_input)
```

### 测试要求

- 所有测试必须通过：`pytest tests/ -x`
- 代码检查必须通过：`ruff check src/ tests/`
- 不要提交会破坏现有测试的代码
- 覆盖率目标：核心模块 >= 80%

---

## 扩展开发（Y.E.S. 标准）

YuanBot Extension Standard (Y.E.S.) 是扩展开发的规范。详见：

- 规范文档：[docs/development-standards-ecosystem.md](docs/development-standards-ecosystem.md)
- 参考实现：[src/yuanbot/services/extension_standard.py](src/yuanbot/services/extension_standard.py)

### 扩展类型

| 类型 | 前缀 | 说明 | 核心接口文件 |
|------|------|------|-------------|
| AI Provider | `yuanbot-ai-provider-` | 新的 AI 后端 | `adapter.py` |
| Channel | `yuanbot-channel-` | 新的消息通道 | `adapter.py` |
| Skill | `yuanbot-skill-` | 对话技能模块 | `definition.yaml` |
| Tool | `yuanbot-tool-` | 外部工具 | `schema.json` + `executor.py` |
| Persona | `yuanbot-persona-` | 人设包 | `persona.yaml` |

### 扩展目录结构

```
yuanbot-<type>-<name>/
├── manifest.json          # 必须：扩展元数据
├── README.md              # 必须：使用文档
├── LICENSE                # 必须：开源协议
├── changelog.md           # 推荐：更新日志
├── icon.png               # 推荐：扩展图标 (512x512)
└── src/                   # 必须：源代码目录
    ├── adapter.py         # 或 definition.yaml / schema.json 等
    └── ...
```

### 使用脚手架快速创建

```python
from yuanbot.services.extension_standard import create_scaffold
create_scaffold("skill", "my_skill", "extensions/")
```

或使用 CLI（如有实现）：

```bash
yuanbot-cli create --type skill --name my_skill
```

---

## 文档贡献

文档位于 `docs/` 目录，使用 MkDocs 构建。贡献文档：

1. 修改或新增 `docs/` 下的 Markdown 文件
2. 如有新增页面，更新 `mkdocs.yml` 的导航配置
3. 本地预览：`mkdocs serve`
4. 图片资源放在 `docs/assets/` 目录

文档语言：
- `docs/**/*.md` — 中文文档
- `docs/en/**/*.md` — 英文文档（如果你愿意翻译，非常欢迎！）

---

## 报告问题

使用 GitHub Issues 报告 Bug，请包含：

- YuanBot 版本
- Python 版本
- 操作系统
- Docker 版本（如使用 Docker 部署）
- 复现步骤
- 期望行为 vs 实际行为
- 相关日志
- 配置片段（注意隐藏密钥）

---

## 开发流程总结

```
[提 Issue] → [创建分支] → [编写代码+测试] → [本地验证]
                                                      ↓
                                              [提交 PR]
                                                      ↓
                                          [CI 自动检查]
                                           ├── Lint
                                           ├── Test
                                           ├── Build
                                           └── Extension Validate
                                                      ↓
                                          [Code Review]
                                                      ↓
                                          [合并 → 自动发布]
```

---

再次感谢你的贡献！🌟
