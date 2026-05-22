"""扩展标准与版本管理测试"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from yuanbot.services.extension_standard import (
    EXTENSION_TYPES,
    ExtensionManifest,
    ExtensionValidator,
    VersionManager,
    compare_versions,
    create_scaffold,
    is_version_compatible,
    parse_version,
)


class TestVersionParsing:
    """版本号解析测试"""

    def test_parse_standard_version(self):
        """测试标准版本号解析"""
        assert parse_version("1.2.3") == (1, 2, 3)
        assert parse_version("0.1.0") == (0, 1, 0)
        assert parse_version("10.20.30") == (10, 20, 30)

    def test_parse_two_part_version(self):
        """测试两段版本号"""
        assert parse_version("1.2") == (1, 2)
        assert parse_version("0.1") == (0, 1)

    def test_parse_single_part_version(self):
        """测试单段版本号"""
        assert parse_version("1") == (1,)

    def test_parse_version_with_whitespace(self):
        """测试带空格的版本号"""
        assert parse_version(" 1.2.3 ") == (1, 2, 3)

    def test_parse_invalid_version(self):
        """测试无效版本号"""
        assert parse_version("abc") == (0,)
        assert parse_version("1.x.3") == (1, 0, 3)


class TestVersionComparison:
    """版本号比较测试"""

    def test_equal_versions(self):
        """测试相等版本"""
        assert compare_versions("1.0.0", "1.0.0") == 0
        assert compare_versions("2.3.4", "2.3.4") == 0

    def test_less_than(self):
        """测试小于"""
        assert compare_versions("1.0.0", "1.0.1") == -1
        assert compare_versions("1.0.0", "1.1.0") == -1
        assert compare_versions("1.0.0", "2.0.0") == -1

    def test_greater_than(self):
        """测试大于"""
        assert compare_versions("1.0.1", "1.0.0") == 1
        assert compare_versions("1.1.0", "1.0.0") == 1
        assert compare_versions("2.0.0", "1.0.0") == 1

    def test_different_lengths(self):
        """测试不同长度的版本号"""
        assert compare_versions("1.0", "1.0.0") == 0
        assert compare_versions("1.0.1", "1.0") == 1


class TestVersionCompatibility:
    """版本兼容性测试"""

    def test_compatible_same_version(self):
        """测试相同版本兼容"""
        assert is_version_compatible("1.0.0", "1.0.0") is True

    def test_compatible_higher_minor(self):
        """测试更高次版本兼容"""
        assert is_version_compatible("1.0.0", "1.1.0") is True
        assert is_version_compatible("1.0.0", "1.2.3") is True

    def test_incompatible_different_major(self):
        """测试不同主版本不兼容"""
        assert is_version_compatible("1.0.0", "2.0.0") is False
        assert is_version_compatible("2.0.0", "1.0.0") is False

    def test_incompatible_lower_version(self):
        """测试更低版本不兼容"""
        assert is_version_compatible("1.2.0", "1.1.0") is False

    def test_empty_versions(self):
        """测试空版本号"""
        assert is_version_compatible("", "1.0.0") is True
        assert is_version_compatible("1.0.0", "") is True


class TestExtensionManifestValidation:
    """扩展清单验证测试"""

    def test_valid_manifest(self):
        """测试有效清单"""
        manifest = ExtensionManifest(
            type="skill",
            id="test_skill",
            name="Test Skill",
            version="1.0.0",
        )
        errors = manifest.validate()
        assert len(errors) == 0

    def test_missing_required_fields(self):
        """测试缺少必填字段"""
        manifest = ExtensionManifest(
            type="",
            id="",
            name="",
            version="",
        )
        errors = manifest.validate()
        assert len(errors) >= 3  # type, id, name

    def test_invalid_type(self):
        """测试无效类型"""
        manifest = ExtensionManifest(
            type="invalid_type",
            id="test",
            name="Test",
            version="1.0.0",
        )
        errors = manifest.validate()
        assert any("Invalid type" in e for e in errors)

    def test_ai_provider_requires_models(self):
        """测试 AI 提供商必须声明支持的模型"""
        manifest = ExtensionManifest(
            type="ai_provider",
            id="test_ai",
            name="Test AI",
            version="1.0.0",
            supported_models=[],
        )
        errors = manifest.validate()
        assert any("supported_models" in e for e in errors)

    def test_channel_requires_platform(self):
        """测试通道必须声明平台"""
        manifest = ExtensionManifest(
            type="channel",
            id="test_channel",
            name="Test Channel",
            version="1.0.0",
            platform="",
        )
        errors = manifest.validate()
        assert any("platform" in e for e in errors)

    def test_tool_permission_level(self):
        """测试工具权限级别验证"""
        manifest = ExtensionManifest(
            type="tool",
            id="test_tool",
            name="Test Tool",
            version="1.0.0",
            permission_level="invalid",
        )
        errors = manifest.validate()
        assert any("permission_level" in e for e in errors)

    def test_version_format_validation(self):
        """测试版本号格式验证"""
        manifest = ExtensionManifest(
            type="skill",
            id="test",
            name="Test",
            version="1",  # 只有主版本号
        )
        errors = manifest.validate()
        assert any("major.minor" in e for e in errors)

    def test_manifest_roundtrip(self):
        """测试清单序列化/反序列化"""
        manifest = ExtensionManifest(
            type="skill",
            id="test_skill",
            name="Test Skill",
            version="1.0.0",
            description="A test skill",
            author="tester",
            dependencies=["dep1:1.0.0"],
        )
        d = manifest.to_dict()
        restored = ExtensionManifest.from_dict(d)
        assert restored.type == manifest.type
        assert restored.id == manifest.id
        assert restored.version == manifest.version
        assert restored.dependencies == manifest.dependencies


class TestVersionManager:
    """版本管理器测试"""

    def test_check_dependencies_satisfied(self):
        """测试依赖满足"""
        manifest = ExtensionManifest(
            type="skill",
            id="test",
            name="Test",
            version="1.0.0",
            dependencies=["dep1:1.0.0"],
        )
        installed = {"dep1": "1.2.0"}
        errors = VersionManager.check_dependencies(manifest, installed)
        assert len(errors) == 0

    def test_check_dependencies_missing(self):
        """测试缺少依赖"""
        manifest = ExtensionManifest(
            type="skill",
            id="test",
            name="Test",
            version="1.0.0",
            dependencies=["dep1:1.0.0"],
        )
        installed: dict[str, str] = {}
        errors = VersionManager.check_dependencies(manifest, installed)
        assert len(errors) == 1
        assert "Missing dependency" in errors[0]

    def test_check_dependencies_version_mismatch(self):
        """测试依赖版本不匹配"""
        manifest = ExtensionManifest(
            type="skill",
            id="test",
            name="Test",
            version="1.0.0",
            dependencies=["dep1:2.0.0"],
        )
        installed = {"dep1": "1.0.0"}
        errors = VersionManager.check_dependencies(manifest, installed)
        assert len(errors) == 1
        assert "version mismatch" in errors[0]

    def test_check_dependencies_without_version(self):
        """测试无版本约束的依赖"""
        manifest = ExtensionManifest(
            type="skill",
            id="test",
            name="Test",
            version="1.0.0",
            dependencies=["dep1"],
        )
        installed = {"dep1": "1.0.0"}
        errors = VersionManager.check_dependencies(manifest, installed)
        assert len(errors) == 0

    def test_check_update_available(self):
        """测试更新检测"""
        assert VersionManager.check_update_available("1.0.0", "1.0.1") is True
        assert VersionManager.check_update_available("1.0.0", "2.0.0") is True
        assert VersionManager.check_update_available("1.0.0", "1.0.0") is False
        assert VersionManager.check_update_available("1.0.1", "1.0.0") is False


class TestExtensionValidator:
    """扩展验证器测试"""

    def test_validate_nonexistent_dir(self):
        """测试验证不存在的目录"""
        errors = ExtensionValidator.validate_extension_dir("/nonexistent/path")
        assert len(errors) > 0
        assert "does not exist" in errors[0]

    def test_validate_missing_manifest(self):
        """测试缺少 manifest.json"""
        with tempfile.TemporaryDirectory() as tmpdir:
            errors = ExtensionValidator.validate_extension_dir(tmpdir)
            assert any("manifest.json" in e for e in errors)

    def test_validate_skill_extension(self):
        """测试验证技能扩展"""
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = Path(tmpdir) / "test_skill"
            ext_dir.mkdir()

            manifest = {
                "type": "skill",
                "id": "test_skill",
                "name": "Test Skill",
                "version": "1.0.0",
            }
            (ext_dir / "manifest.json").write_text(json.dumps(manifest))
            (ext_dir / "definition.yaml").write_text("skill_id: test_skill\n")

            errors = ExtensionValidator.validate_extension_dir(ext_dir)
            # 可能有 README 警告，但不应有错误
            real_errors = [e for e in errors if "README" not in e]
            assert len(real_errors) == 0

    def test_validate_tool_extension(self):
        """测试验证工具扩展"""
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = Path(tmpdir) / "test_tool"
            ext_dir.mkdir()

            manifest = {
                "type": "tool",
                "id": "test_tool",
                "name": "Test Tool",
                "version": "1.0.0",
                "permission_level": "safe",
            }
            (ext_dir / "manifest.json").write_text(json.dumps(manifest))
            (ext_dir / "schema.json").write_text("{}")
            (ext_dir / "executor.py").write_text("async def execute(params): pass")

            errors = ExtensionValidator.validate_extension_dir(ext_dir)
            real_errors = [e for e in errors if "README" not in e]
            assert len(real_errors) == 0

    def test_validate_persona_extension(self):
        """测试验证人设扩展"""
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = Path(tmpdir) / "test_persona"
            ext_dir.mkdir()

            manifest = {
                "type": "persona",
                "id": "test_persona",
                "name": "Test Persona",
                "version": "1.0.0",
            }
            (ext_dir / "manifest.json").write_text(json.dumps(manifest))
            (ext_dir / "persona.yaml").write_text("persona_id: test\n")

            errors = ExtensionValidator.validate_extension_dir(ext_dir)
            real_errors = [e for e in errors if "README" not in e]
            assert len(real_errors) == 0


class TestCreateScaffold:
    """脚手架创建测试"""

    def test_create_skill_scaffold(self):
        """测试创建技能脚手架"""
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = create_scaffold("skill", "my_skill", tmpdir)
            assert ext_dir.exists()
            assert (ext_dir / "manifest.json").exists()
            assert (ext_dir / "definition.yaml").exists()
            assert (ext_dir / "README.md").exists()

            manifest = ExtensionManifest.from_file(ext_dir / "manifest.json")
            assert manifest.type == "skill"
            assert manifest.id == "my_skill"
            assert manifest.version == "1.0.0"

    def test_create_tool_scaffold(self):
        """测试创建工具脚手架"""
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = create_scaffold("tool", "my_tool", tmpdir)
            assert (ext_dir / "schema.json").exists()
            assert (ext_dir / "executor.py").exists()

    def test_create_persona_scaffold(self):
        """测试创建人设脚手架"""
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_dir = create_scaffold("persona", "my_persona", tmpdir)
            assert (ext_dir / "persona.yaml").exists()

    def test_create_invalid_type(self):
        """测试无效类型"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="Invalid extension type"):
                create_scaffold("invalid", "test", tmpdir)

    def test_all_extension_types_covered(self):
        """测试所有扩展类型都有定义"""
        expected_types = {"ai_provider", "channel", "skill", "tool", "persona"}
        assert set(EXTENSION_TYPES.keys()) == expected_types
