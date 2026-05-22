# 贡献指南

感谢你对 YuanBot 项目的关注！以下是参与贡献的指南。

## 开发环境

```bash
git clone https://github.com/your-org/yuanbot.git
cd yuanbot
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 提交规范

### 分支命名

- `feature/xxx` — 新功能
- `fix/xxx` — Bug 修复
- `docs/xxx` — 文档更新
- `refactor/xxx` — 重构

### Commit Message

采用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
<type>(<scope>): <description>

[optional body]
```

类型：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档
- `style`: 代码格式（不影响逻辑）
- `refactor`: 重构
- `test`: 测试
- `chore`: 构建/工具变更

示例：
```
feat(memory): add semantic memory retrieval by embedding similarity
fix(gateway): handle empty platform_user_id in identity resolution
docs(architecture): update memory system diagram
```

## 代码规范

### 风格

- 使用 `ruff` 进行 lint 和格式化
- 行宽 100 字符
- Python 3.12+，积极使用新特性（`type` 语句、`match` 等）

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

## 测试

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

### 运行测试

```bash
# 全部测试
pytest tests/ -v

# 特定文件
pytest tests/test_memory/test_manager.py -v

# 带覆盖率
pytest tests/ --cov=yuanbot --cov-report=term-missing
```

### 测试要求

- 所有测试必须通过：`pytest tests/ -x`
- 代码检查必须通过：`ruff check src/ tests/`
- 不要提交会破坏现有测试的代码

## Pull Request 流程

1. Fork 项目并创建分支
2. 编写代码和测试
3. 确保 `pytest` 和 `ruff check` 通过
4. 提交 PR，填写说明
5. 等待 Code Review
6. 合并后删除分支

### PR 说明模板

```markdown
## 变更说明

简述此 PR 做了什么。

## 变更类型

- [ ] 新功能
- [ ] Bug 修复
- [ ] 文档更新
- [ ] 重构

## 测试

- [ ] 新增测试用例
- [ ] 所有测试通过
- [ ] ruff check 通过

## 关联 Issue

Closes #xxx
```

## 扩展开发

参见 [YuanBot Extension Standard](src/yuanbot/services/extension_standard.py)。

扩展类型：
- **AI Provider**: 新的 AI 提供商适配器
- **Channel**: 新的消息通道适配器
- **Skill**: 对话技能
- **Tool**: 外部工具
- **Persona**: 人设包

使用脚手架：
```python
from yuanbot.services.extension_standard import create_scaffold
create_scaffold("skill", "my_skill", "extensions/")
```

## 报告问题

使用 GitHub Issues 报告 Bug，请包含：
- YuanBot 版本
- Python 版本
- 操作系统
- 复现步骤
- 期望行为 vs 实际行为
- 相关日志

## 行为准则

- 尊重所有参与者
- 建设性地提出反馈
- 专注于对社区最有利的事情
- 对他人表示同理心
