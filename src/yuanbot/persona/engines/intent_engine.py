"""意图识别引擎

识别用户输入的核心意图，为后续决策和能力选择提供基础分类。

提供两种实现：
- IntentEngine: 基于规则的意图识别（零依赖）
- MLIntentClassifier: 基于本地 ONNX 模型的意图识别（可选依赖 onnxruntime + tokenizers）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 可选依赖：ONNX 推理
try:
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    _HAS_ONNX = True
except ImportError:
    _HAS_ONNX = False


@dataclass
class IntentResult:
    """意图识别结果"""

    primary: str  # 主要意图
    secondary: list[str] = field(default_factory=list)  # 次要意图
    confidence: float = 0.5  # 置信度 0.0 ~ 1.0
    entities: dict[str, Any] = field(default_factory=dict)  # 提取的实体


# 意图模式定义
_INTENT_PATTERNS: dict[str, dict[str, Any]] = {
    "greeting": {
        "keywords": ["你好", "hi", "hello", "嗨", "早上好", "晚上好", "早安", "晚安"],
        "priority": 1,
    },
    "farewell": {
        "keywords": ["再见", "拜拜", "bye", "byebye", "晚安", "下次见"],
        "priority": 1,
    },
    "emotional_seeking_comfort": {
        "keywords": [
            "难过",
            "伤心",
            "不开心",
            "烦",
            "压力大",
            "焦虑",
            "害怕",
            "孤独",
            "失落",
            "委屈",
            "想哭",
            "崩溃",
        ],
        "priority": 3,
    },
    "emotional_sharing_joy": {
        "keywords": [
            "开心",
            "高兴",
            "太好了",
            "哈哈",
            "恭喜",
            "棒",
            "厉害",
            "成功",
            "通过了",
            "拿到了",
        ],
        "priority": 2,
    },
    "seeking_advice": {
        "keywords": ["怎么办", "你觉得", "建议", "意见", "帮我", "应该怎么", "有什么办法"],
        "priority": 2,
    },
    "casual_chat": {
        "keywords": ["无聊", "聊聊", "在干嘛", "你在吗", "说说", "讲讲"],
        "priority": 1,
    },
    "asking_question": {
        "keywords": ["什么", "为什么", "怎么", "哪里", "谁", "几", "吗", "？"],
        "priority": 1,
    },
    "request_action": {
        "keywords": ["帮我", "提醒我", "设置", "创建", "搜索", "查一下", "打开"],
        "priority": 2,
    },
    "expressing_gratitude": {
        "keywords": ["谢谢", "感谢", "多谢", "thank", "thx"],
        "priority": 1,
    },
}

# 命令模式（高置信度直接匹配，预编译正则）
_COMMAND_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^/set_reminder"), "set_reminder"),
    (re.compile(r"^/search"), "search"),
    (re.compile(r"^/translate"), "translate"),
    (re.compile(r"^/help"), "help"),
    (re.compile(r"^/status"), "status"),
    (re.compile(r"^/memory"), "memory_query"),
]


class IntentEngine:
    """意图识别引擎

    实现方式：
    1. 规则优先：命令式意图直接匹配
    2. 关键词匹配：基于意图词典
    3. 可扩展：后续接入模型分类器
    """

    def __init__(self, custom_patterns: dict[str, dict[str, Any]] | None = None):
        self._patterns = {**_INTENT_PATTERNS, **(custom_patterns or {})}

    def recognize(self, text: str) -> IntentResult:
        """识别用户意图

        Args:
            text: 用户输入文本

        Returns:
            IntentResult: 意图识别结果
        """
        if not text or not text.strip():
            return IntentResult(primary="empty", confidence=1.0)

        text_clean = text.strip()
        text_lower = text_clean.lower()

        # 1. 命令模式匹配（高置信度，使用预编译正则）
        for pattern, intent in _COMMAND_PATTERNS:
            if pattern.match(text_clean):
                return IntentResult(
                    primary=intent,
                    confidence=0.99,
                    entities={"command": text_clean.split()[0]},
                )

        # 2. 关键词匹配
        scores: dict[str, float] = {}
        matched_keywords: dict[str, list[str]] = {}

        for intent, config in self._patterns.items():
            keywords = config.get("keywords", [])
            priority = config.get("priority", 1)
            matched = [kw for kw in keywords if kw in text_lower]

            if matched:
                # 分数 = 匹配数量 * 优先级权重
                score = len(matched) * (priority * 0.3)
                scores[intent] = min(score, 1.0)
                matched_keywords[intent] = matched

        if not scores:
            return IntentResult(primary="unknown", confidence=0.3)

        # 按分数排序
        sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        primary = sorted_intents[0][0]
        confidence = min(sorted_intents[0][1], 1.0)
        secondary = [intent for intent, _ in sorted_intents[1:3]]  # 最多2个次要意图

        # 提取实体
        entities: dict[str, Any] = {}
        if primary in matched_keywords:
            entities["matched_keywords"] = matched_keywords[primary]

        result = IntentResult(
            primary=primary,
            secondary=secondary,
            confidence=confidence,
            entities=entities,
        )

        logger.debug(
            "intent_recognized",
            primary=primary,
            confidence=confidence,
            secondary=secondary,
        )

        return result


class MLIntentClassifier:
    """基于本地 ONNX 模型的意图分类器

    使用 ONNX Runtime 加载预训练的文本分类模型，
    配合 tokenizer 进行文本编码，实现意图分类。
    当模型不可用时自动 fallback 到规则引擎。

    模型要求：
    - ONNX 格式，输出 logits（shape: [1, num_labels]）
    - 配套 tokenizer.json（HuggingFace tokenizers 格式）
    - labels.json（可选，标签名称列表）

    用法::

        classifier = MLIntentClassifier(
            model_path="models/intent_model.onnx",
            tokenizer_path="models/tokenizer.json",
            labels_path="models/labels.json",  # 可选
        )
        result = classifier.classify("你好呀")
    """

    def __init__(
        self,
        model_path: str | Path,
        tokenizer_path: str | Path,
        labels_path: str | Path | None = None,
        fallback_engine: IntentEngine | None = None,
        confidence_threshold: float = 0.5,
    ):
        """初始化 ML 意图分类器

        Args:
            model_path: ONNX 模型文件路径
            tokenizer_path: tokenizer.json 文件路径
            labels_path: labels.json 文件路径（可选）
            fallback_engine: 当模型不可用时的 fallback 引擎
            confidence_threshold: 低于此阈值时使用 fallback
        """
        self._model_path = Path(model_path)
        self._tokenizer_path = Path(tokenizer_path)
        self._labels_path = Path(labels_path) if labels_path else None
        self._fallback = fallback_engine or IntentEngine()
        self._confidence_threshold = confidence_threshold

        self._session: Any = None
        self._tokenizer: Any = None
        self._labels: list[str] = []
        self._ready = False

        self._try_load()

    def _try_load(self) -> None:
        """尝试加载模型和 tokenizer，失败则保持未就绪状态"""
        if not _HAS_ONNX:
            logger.warning(
                "ml_intent_deps_missing",
                msg="onnxruntime or tokenizers not installed, using fallback",
            )
            return

        try:
            if not self._model_path.exists():
                logger.warning(
                    "ml_intent_model_not_found",
                    path=str(self._model_path),
                )
                return

            if not self._tokenizer_path.exists():
                logger.warning(
                    "ml_intent_tokenizer_not_found",
                    path=str(self._tokenizer_path),
                )
                return

            # 加载 ONNX 模型
            sess_options = ort.SessionOptions()
            sess_options.log_severity_level = 3  # 只显示错误
            self._session = ort.InferenceSession(
                str(self._model_path),
                sess_options=sess_options,
            )

            # 加载 tokenizer
            self._tokenizer = Tokenizer.from_file(str(self._tokenizer_path))

            # 加载标签
            if self._labels_path and self._labels_path.exists():
                import json

                self._labels = json.loads(self._labels_path.read_text(encoding="utf-8"))
            else:
                # 尝试从模型输出维度推断
                output_shape = self._session.get_outputs()[0].shape
                if len(output_shape) >= 2:
                    num_labels = output_shape[-1]
                    self._labels = [f"intent_{i}" for i in range(num_labels)]

            self._ready = True
            logger.info(
                "ml_intent_model_loaded",
                model=str(self._model_path),
                num_labels=len(self._labels),
            )

        except Exception as e:
            logger.error(
                "ml_intent_load_failed",
                error=str(e),
            )
            self._ready = False

    @property
    def is_ready(self) -> bool:
        """模型是否已加载就绪"""
        return self._ready

    def classify(self, text: str) -> IntentResult:
        """对输入文本进行意图分类

        当模型未就绪或置信度低于阈值时，自动 fallback 到规则引擎。

        Args:
            text: 用户输入文本

        Returns:
            IntentResult: 意图分类结果
        """
        if not text or not text.strip():
            return IntentResult(primary="empty", confidence=1.0)

        if not self._ready:
            logger.debug("ml_intent_not_ready_using_fallback")
            return self._fallback.recognize(text)

        try:
            # Tokenize
            encoding = self._tokenizer.encode(text.strip())
            input_ids = encoding.ids
            attention_mask = [1] * len(input_ids)

            # 构建模型输入
            input_name = self._session.get_inputs()[0].name
            inputs = {
                input_name: np.array([input_ids], dtype=np.int64),
            }

            # 如果模型需要 attention_mask
            if len(self._session.get_inputs()) > 1:
                mask_name = self._session.get_inputs()[1].name
                inputs[mask_name] = np.array([attention_mask], dtype=np.int64)

            # 推理
            outputs = self._session.run(None, inputs)
            logits = outputs[0][0]  # shape: [num_labels]

            # Softmax
            exp_logits = np.exp(logits - np.max(logits))
            probs = exp_logits / exp_logits.sum()

            # 获取最高概率
            best_idx = int(np.argmax(probs))
            confidence = float(probs[best_idx])

            primary = self._labels[best_idx] if best_idx < len(self._labels) else "unknown"

            # 次要意图（top-3，排除 primary）
            sorted_indices = np.argsort(probs)[::-1]
            secondary = [
                self._labels[i]
                for i in sorted_indices[1:3]
                if i < len(self._labels) and probs[i] > 0.1
            ]

            result = IntentResult(
                primary=primary,
                secondary=secondary,
                confidence=confidence,
                entities={"source": "ml_model"},
            )

            # 低置信度时 fallback
            if confidence < self._confidence_threshold:
                logger.debug(
                    "ml_intent_low_confidence",
                    ml_primary=primary,
                    ml_confidence=confidence,
                    threshold=self._confidence_threshold,
                )
                fallback_result = self._fallback.recognize(text)
                # 取置信度更高的结果
                if fallback_result.confidence > confidence:
                    fallback_result.entities["ml_primary"] = primary
                    fallback_result.entities["ml_confidence"] = confidence
                    return fallback_result

            return result

        except Exception as e:
            logger.error(
                "ml_intent_inference_error",
                error=str(e),
            )
            return self._fallback.recognize(text)

    def get_model_info(self) -> dict[str, Any]:
        """获取模型信息"""
        info: dict[str, Any] = {
            "ready": self._ready,
            "model_path": str(self._model_path),
            "tokenizer_path": str(self._tokenizer_path),
            "num_labels": len(self._labels),
            "confidence_threshold": self._confidence_threshold,
            "has_onnx_deps": _HAS_ONNX,
        }
        if self._ready:
            info["labels"] = self._labels
            info["model_inputs"] = [
                {"name": inp.name, "shape": inp.shape, "type": inp.type}
                for inp in self._session.get_inputs()
            ]
        return info
