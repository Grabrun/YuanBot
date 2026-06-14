# 参与贡献

感谢你对 YuanBot 的关注！我们欢迎所有形式的贡献。

## 贡献方式

### 🐛 报告 Bug

在 [GitHub Issues](https://github.com/Grabrun/YuanBot/issues/new) 提交 Bug 报告时，请包含：

- 清晰的标题和描述
- 复现步骤
- 预期行为和实际行为
- 环境信息（操作系统、Python 版本等）
- 日志或截图（如有）

### 💡 提出新功能

在 [Discussions](https://github.com/Grabrun/YuanBot/discussions) 中提出功能建议时，请描述：

- 你想解决的问题
- 你期望的实现方式
- 是否有替代方案

### 📝 提交代码

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feat/amazing-feature`
3. 提交变更：`git commit -m 'feat: add amazing feature'`
4. 推送到分支：`git push origin feat/amazing-feature`
5. 提交 Pull Request

### 📖 完善文档

文档改进和翻译工作同样欢迎！直接在 `docs/` 或 `docs-vitepress/` 中修改并提交 PR。

## 开发环境设置

```bash
git clone https://github.com/Grabrun/YuanBot.git
cd YuanBot
uv sync --all-extras
yuanbot version
```

## 代码规范

- 遵循现有的代码风格
- 添加必要的测试
- 确保所有测试通过
- 更新相关文档

## 提交规范

我们使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档变更
- `refactor:` 重构
- `test:` 测试
- `chore:` 杂项

## 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_memory.py

# 查看测试覆盖率
pytest --cov=yuanbot
```

## 行为准则

请保持友善、尊重和有建设性的沟通。详细内容请参阅 [CODE_OF_CONDUCT](https://github.com/Grabrun/YuanBot/blob/main/CODE_OF_CONDUCT.md)。

---

**🌸 每一份贡献都让 YuanBot 变得更好！**
