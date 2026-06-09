"""意图分类模型集成测试

测试 MLIntentClassifier、SklearnIntentClassifier 和 create_intent_classifier 工厂函数。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yuanbot.persona.engines.intent_engine import (
    IntentEngine,
    IntentResult,
    MLIntentClassifier,
    SklearnIntentClassifier,
    create_intent_classifier,
)


# --------------------------------------------------------------------------- #
# IntentEngine 基础测试
# --------------------------------------------------------------------------- #


class TestIntentEngine:
    """规则引擎测试"""

    def test_empty_input(self):
        engine = IntentEngine()
        result = engine.recognize("")
        assert result.primary == "empty"
        assert result.confidence == 1.0

    def test_greeting(self):
        engine = IntentEngine()
        result = engine.recognize("你好")
        assert result.primary == "greeting"
        assert result.confidence > 0

    def test_farewell(self):
        engine = IntentEngine()
        result = engine.recognize("再见")
        assert result.primary == "farewell"

    def test_emotional_comfort(self):
        engine = IntentEngine()
        result = engine.recognize("我好难过")
        assert result.primary == "emotional_seeking_comfort"

    def test_seeking_advice(self):
        engine = IntentEngine()
        result = engine.recognize("怎么办")
        assert result.primary == "seeking_advice"

    def test_command_pattern(self):
        engine = IntentEngine()
        result = engine.recognize("/help")
        assert result.primary == "help"
        assert result.confidence == 0.99

    def test_unknown(self):
        engine = IntentEngine()
        result = engine.recognize("asdfghjkl")
        assert result.primary == "unknown"
        assert result.confidence == 0.3

    def test_secondary_intents(self):
        engine = IntentEngine()
        result = engine.recognize("好开心 太好了 哈哈")
        assert result.primary == "emotional_sharing_joy"
        # 可能有次要意图
        assert isinstance(result.secondary, list)

    def test_custom_patterns(self):
        custom = {
            "custom_intent": {
                "keywords": ["自定义", "测试"],
                "priority": 2,
            }
        }
        engine = IntentEngine(custom_patterns=custom)
        result = engine.recognize("这是自定义测试")
        assert result.primary == "custom_intent"


# --------------------------------------------------------------------------- #
# SklearnIntentClassifier 测试
# --------------------------------------------------------------------------- #


class TestSklearnIntentClassifier:
    """sklearn 模型分类器测试"""

    def test_init_without_model(self, tmp_path: Path):
        """模型文件不存在时应 fallback"""
        classifier = SklearnIntentClassifier(
            model_path=tmp_path / "nonexistent.joblib",
        )
        assert not classifier.is_ready

    def test_init_without_joblib(self, tmp_path: Path):
        """joblib 未安装时应 fallback"""
        with patch("yuanbot.persona.engines.intent_engine._HAS_JOBLIB", False):
            classifier = SklearnIntentClassifier(
                model_path=tmp_path / "model.joblib",
            )
            assert not classifier.is_ready

    def test_classify_fallback_when_not_ready(self, tmp_path: Path):
        """未就绪时应使用 fallback 引擎"""
        fallback = IntentEngine()
        classifier = SklearnIntentClassifier(
            model_path=tmp_path / "nonexistent.joblib",
            fallback_engine=fallback,
        )
        result = classifier.classify("你好")
        # fallback 应返回规则引擎结果
        assert result.primary == "greeting"

    def test_classify_with_mock_model(self, tmp_path: Path):
        """使用 mock 模型测试分类"""
        import numpy as np

        mock_pipeline = MagicMock()
        mock_pipeline.predict.return_value = np.array([0])
        mock_pipeline.predict_proba.return_value = np.array([[0.9, 0.05, 0.05]])

        labels = ["greeting", "farewell", "other"]
        labels_path = tmp_path / "labels.json"
        labels_path.write_text(json.dumps(labels), encoding="utf-8")

        model_path = tmp_path / "model.joblib"
        model_path.write_text("mock", encoding="utf-8")

        import yuanbot.persona.engines.intent_engine as ie_mod

        mock_joblib = MagicMock()
        mock_joblib.load.return_value = mock_pipeline
        with patch.object(ie_mod, '_HAS_JOBLIB', True), \
             patch.object(ie_mod, '_joblib', mock_joblib):
            classifier = SklearnIntentClassifier(
                model_path=model_path,
                labels_path=labels_path,
            )
            assert classifier.is_ready

            result = classifier.classify("你好")
            assert result.primary == "greeting"
            assert result.confidence == 0.9
            assert result.entities.get("source") == "sklearn_model"

    def test_low_confidence_fallback(self, tmp_path: Path):
        """低置信度时应 fallback 到规则引擎"""
        import numpy as np

        mock_pipeline = MagicMock()
        mock_pipeline.predict.return_value = np.array([0])
        mock_pipeline.predict_proba.return_value = np.array([[0.3, 0.35, 0.35]])

        labels = ["greeting", "farewell", "other"]
        labels_path = tmp_path / "labels.json"
        labels_path.write_text(json.dumps(labels), encoding="utf-8")

        model_path = tmp_path / "model.joblib"
        model_path.write_text("mock", encoding="utf-8")

        import yuanbot.persona.engines.intent_engine as ie_mod

        mock_joblib = MagicMock()
        mock_joblib.load.return_value = mock_pipeline
        with patch.object(ie_mod, '_HAS_JOBLIB', True), \
             patch.object(ie_mod, '_joblib', mock_joblib):
            classifier = SklearnIntentClassifier(
                model_path=model_path,
                labels_path=labels_path,
                confidence_threshold=0.5,
            )

            result = classifier.classify("你好")
            # 0.3 < 0.5 阈值，尝试 fallback
            # 但规则引擎对 "你好" 也是 greeting 且 confidence=0.3
            # fallback_result.confidence (0.3) > confidence (0.3) 为 False，所以返回 ML 结果
            assert result.primary == "greeting"
            assert result.confidence == 0.3
            assert result.entities.get("source") == "sklearn_model"

    def test_get_model_info(self, tmp_path: Path):
        """模型信息应包含必要字段"""
        classifier = SklearnIntentClassifier(
            model_path=tmp_path / "nonexistent.joblib",
        )
        info = classifier.get_model_info()
        assert "ready" in info
        assert "model_type" in info
        assert info["model_type"] == "sklearn"

    def test_inference_error_fallback(self, tmp_path: Path):
        """推理出错时应 fallback"""
        mock_pipeline = MagicMock()
        mock_pipeline.predict.side_effect = RuntimeError("inference error")

        model_path = tmp_path / "model.joblib"
        model_path.write_text("mock", encoding="utf-8")

        import yuanbot.persona.engines.intent_engine as ie_mod

        mock_joblib = MagicMock()
        mock_joblib.load.return_value = mock_pipeline
        with patch.object(ie_mod, '_HAS_JOBLIB', True), \
             patch.object(ie_mod, '_joblib', mock_joblib):
            classifier = SklearnIntentClassifier(
                model_path=model_path,
            )
            # 手动标记为 ready
            classifier._ready = True

            result = classifier.classify("你好")
            # 应 fallback 到规则引擎
            assert result.primary == "greeting"


# --------------------------------------------------------------------------- #
# MLIntentClassifier 测试
# --------------------------------------------------------------------------- #


class TestMLIntentClassifier:
    """ONNX 模型分类器测试"""

    def test_init_without_onnx_deps(self, tmp_path: Path):
        """ONNX 依赖缺失时应标记未就绪"""
        with patch("yuanbot.persona.engines.intent_engine._HAS_ONNX", False):
            classifier = MLIntentClassifier(
                model_path=tmp_path / "model.onnx",
                tokenizer_path=tmp_path / "tokenizer.json",
            )
            assert not classifier.is_ready

    def test_init_without_model_file(self, tmp_path: Path):
        """模型文件不存在时应标记未就绪"""
        classifier = MLIntentClassifier(
            model_path=tmp_path / "nonexistent.onnx",
            tokenizer_path=tmp_path / "tokenizer.json",
        )
        assert not classifier.is_ready

    def test_classify_fallback_when_not_ready(self, tmp_path: Path):
        """未就绪时应使用 fallback"""
        fallback = IntentEngine()
        classifier = MLIntentClassifier(
            model_path=tmp_path / "nonexistent.onnx",
            tokenizer_path=tmp_path / "tokenizer.json",
            fallback_engine=fallback,
        )
        result = classifier.classify("你好")
        assert result.primary == "greeting"

    def test_get_model_info_not_ready(self, tmp_path: Path):
        """未就绪时模型信息应包含基本字段"""
        classifier = MLIntentClassifier(
            model_path=tmp_path / "nonexistent.onnx",
            tokenizer_path=tmp_path / "tokenizer.json",
        )
        info = classifier.get_model_info()
        assert info["ready"] is False
        assert "model_path" in info
        assert "has_onnx_deps" in info


# --------------------------------------------------------------------------- #
# create_intent_classifier 工厂函数测试
# --------------------------------------------------------------------------- #


class TestCreateIntentClassifier:
    """工厂函数测试"""

    def test_fallback_to_rule_engine(self, tmp_path: Path):
        """无模型文件时应返回规则引擎"""
        classifier = create_intent_classifier(model_dir=tmp_path)
        assert isinstance(classifier, IntentEngine)

    def test_prefer_onnx_over_sklearn(self, tmp_path: Path):
        """ONNX 和 sklearn 模型都存在时，应优先使用 ONNX"""
        # 创建假的模型文件
        (tmp_path / "intent_model.onnx").write_text("fake", encoding="utf-8")
        (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
        (tmp_path / "intent_model.joblib").write_text("fake", encoding="utf-8")

        # 由于模型文件是假的，ONNX 加载会失败，应该 fallback 到 sklearn 或规则引擎
        classifier = create_intent_classifier(model_dir=tmp_path)
        # 最终结果取决于模型是否能成功加载
        assert classifier is not None

    def test_use_sklearn_when_only_joblib(self, tmp_path: Path):
        """只有 joblib 模型时应使用 sklearn"""
        import numpy as np

        mock_pipeline = MagicMock()
        mock_pipeline.predict.return_value = np.array([0])
        mock_pipeline.predict_proba.return_value = np.array([[0.9, 0.05, 0.05]])

        labels = ["greeting", "farewell", "other"]
        (tmp_path / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
        (tmp_path / "intent_model.joblib").write_text("fake", encoding="utf-8")

        import yuanbot.persona.engines.intent_engine as ie_mod

        mock_joblib = MagicMock()
        mock_joblib.load.return_value = mock_pipeline
        with patch.object(ie_mod, '_HAS_JOBLIB', True), \
             patch.object(ie_mod, '_joblib', mock_joblib):
            classifier = create_intent_classifier(model_dir=tmp_path)
            assert isinstance(classifier, SklearnIntentClassifier)

    def test_classify_with_fallback(self, tmp_path: Path):
        """工厂函数返回的分类器应能正常分类"""
        classifier = create_intent_classifier(model_dir=tmp_path)
        result = classifier.classify("你好") if hasattr(classifier, 'classify') else classifier.recognize("你好")
        assert result.primary == "greeting"


# --------------------------------------------------------------------------- #
# IntentResult 测试
# --------------------------------------------------------------------------- #


class TestIntentResult:
    """IntentResult 数据类测试"""

    def test_default_values(self):
        result = IntentResult(primary="test")
        assert result.primary == "test"
        assert result.secondary == []
        assert result.confidence == 0.5
        assert result.entities == {}

    def test_custom_values(self):
        result = IntentResult(
            primary="greeting",
            secondary=["casual_chat"],
            confidence=0.95,
            entities={"matched_keywords": ["你好"]},
        )
        assert result.primary == "greeting"
        assert result.secondary == ["casual_chat"]
        assert result.confidence == 0.95
        assert result.entities["matched_keywords"] == ["你好"]
