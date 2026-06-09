#!/usr/bin/env python3
"""下载并转换中文 BERT 意图分类模型为 ONNX 格式

使用方法:
    # 1. 安装依赖
    pip install transformers onnx onnxruntime tokenizers

    # 2. 下载预训练模型并转换
    python scripts/download_intent_model.py

    # 3. 或者指定自定义输出目录
    python scripts/download_intent_model.py --output models/

模型来源: 使用 HuggingFace 上的中文 BERT 模型微调后导出 ONNX。
如果没有微调模型，会使用基础 bert-base-chinese + 简单分类头。

对于生产环境，建议使用自定义微调的模型。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 意图标签定义（与 IntentEngine 的意图模式一致）
INTENT_LABELS = [
    "greeting",
    "farewell",
    "emotional_seeking_comfort",
    "emotional_sharing_joy",
    "seeking_advice",
    "casual_chat",
    "asking_question",
    "request_action",
    "expressing_gratitude",
    "unknown",
]

# 每个意图的训练样本（中文）
TRAINING_DATA: dict[str, list[str]] = {
    "greeting": [
        "你好", "hi", "hello", "嗨", "早上好", "晚上好", "早安", "晚安",
        "在吗", "在不在", "hey", "哈喽", "您好", "大家好", "喂",
        "早上好呀", "晚上好呀", "你好呀", "嗨嗨", "早上好哦",
    ],
    "farewell": [
        "再见", "拜拜", "bye", "byebye", "晚安", "下次见", "走了",
        "我先走了", "回见", "下次再聊", "先这样吧", "不聊了", "睡觉了",
        "我先睡了", "晚安啦", "拜拜啦", "下次再聊啦",
    ],
    "emotional_seeking_comfort": [
        "我好难过", "心情不好", "不开心", "好烦", "压力好大", "好焦虑",
        "好害怕", "好孤独", "好失落", "好委屈", "想哭", "我要崩溃了",
        "好伤心", "好郁闷", "好沮丧", "好痛苦", "好无助", "好迷茫",
        "我很难过", "今天心情很差", "感觉好糟糕", "我好累",
        "不想活了", "活着好累", "我是不是很没用",
    ],
    "emotional_sharing_joy": [
        "好开心", "太好了", "哈哈", "恭喜", "好棒", "好厉害",
        "成功了", "通过了", "拿到了", "好高兴", "好兴奋", "好幸福",
        "好满足", "好欣慰", "好惊喜", "好感动", "好快乐",
        "今天好开心", "终于成功了", "太棒了", "哈哈哈",
    ],
    "seeking_advice": [
        "怎么办", "你觉得呢", "给点建议", "帮我出出主意", "应该怎么做好",
        "有什么办法", "你认为呢", "该怎么办", "我该怎么选择",
        "你能帮我想想办法吗", "给个建议呗", "你觉得我应该怎么做",
        "有什么好的建议", "我该怎么办", "帮帮我",
    ],
    "casual_chat": [
        "好无聊", "聊聊吧", "你在干嘛", "你在吗", "说点什么",
        "讲讲呗", "陪我聊天", "无聊死了", "好寂寞", "想找人聊天",
        "你在干什么", "今天干嘛了", "有什么好玩的", "给我讲个故事",
        "说个笑话", "你今天怎么样",
    ],
    "asking_question": [
        "这是什么", "为什么", "怎么回事", "在哪里", "谁", "什么时候",
        "是真的吗", "什么意思", "怎么理解", "能解释一下吗",
        "你知道吗", "有没有听说过", "这个怎么用", "怎么操作",
        "怎么设置", "什么是", "你能告诉我",
    ],
    "request_action": [
        "帮我", "提醒我", "帮我设置", "帮我创建", "帮我搜索",
        "帮我查一下", "帮我打开", "帮我翻译", "帮我算一下",
        "帮我记一下", "帮我发", "帮我找", "帮我定",
        "设置一个提醒", "帮我搜索一下", "帮我查查",
    ],
    "expressing_gratitude": [
        "谢谢", "感谢", "多谢", "thank", "thanks", "thx",
        "太感谢了", "非常感谢", "真的太谢谢了", "你真好",
        "辛苦了", "谢谢你的帮助", "多谢多谢", "感激不尽",
        "太谢谢你了", "谢谢你帮我",
    ],
}


def generate_training_data() -> tuple[list[str], list[int]]:
    """生成训练数据

    Returns:
        (texts, labels) - 文本列表和对应的标签索引列表
    """
    texts: list[str] = []
    labels: list[int] = []

    for intent, examples in TRAINING_DATA.items():
        label_idx = INTENT_LABELS.index(intent)
        for text in examples:
            texts.append(text)
            labels.append(label_idx)

    return texts, labels


def create_model_with_sklearn(
    output_dir: Path,
) -> None:
    """使用 sklearn + 转换方式创建简单模型（不依赖 transformers）"""
    try:
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
    except ImportError:
        print("❌ 需要安装 scikit-learn: pip install scikit-learn")
        sys.exit(1)

    print("📦 使用 TF-IDF + LogisticRegression 训练意图分类模型...")

    texts, labels = generate_training_data()

    # 训练 pipeline
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            max_features=5000,
        )),
        ("clf", LogisticRegression(
            max_iter=1000,
            C=1.0,
            multi_class="multinomial",
        )),
    ])
    pipeline.fit(texts, labels)

    # 评估
    from sklearn.metrics import classification_report
    y_pred = pipeline.predict(texts)
    print("\n📊 训练集分类报告:")
    print(classification_report(
        labels, y_pred,
        target_names=INTENT_LABELS,
        zero_division=0,
    ))

    # 保存为 joblib（轻量级方案，不需要 ONNX）
    import joblib
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "intent_model.joblib"
    joblib.dump(pipeline, model_path)

    # 保存标签
    labels_path = output_dir / "labels.json"
    labels_path.write_text(
        json.dumps(INTENT_LABELS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 保存元信息
    meta = {
        "model_type": "sklearn_tfidf_lr",
        "num_labels": len(INTENT_LABELS),
        "labels": INTENT_LABELS,
        "training_samples": len(texts),
        "feature_params": {
            "analyzer": "char_wb",
            "ngram_range": [2, 4],
            "max_features": 5000,
        },
    }
    meta_path = output_dir / "model_meta.json"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n✅ 模型已保存到: {model_path}")
    print(f"   标签文件: {labels_path}")
    print(f"   元信息: {meta_path}")
    print(f"\n💡 使用方式: 在 bot.yaml 中设置 intent_engine.use_ml_model: true")


def create_model_with_transformers(
    output_dir: Path,
    model_name: str = "bert-base-chinese",
) -> None:
    """使用 transformers 微调并导出 ONNX 模型"""
    try:
        import torch
        from torch.utils.data import DataLoader, Dataset
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )
    except ImportError:
        print("❌ 需要安装 transformers 和 torch:")
        print("   pip install transformers torch onnx")
        sys.exit(1)

    print(f"📦 使用 {model_name} 微调意图分类模型...")

    texts, labels = generate_training_data()

    # 加载 tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # 数据集
    class IntentDataset(Dataset):
        def __init__(self, texts: list[str], labels: list[int]):
            self.encodings = tokenizer(
                texts,
                truncation=True,
                padding=True,
                max_length=128,
                return_tensors="pt",
            )
            self.labels = torch.tensor(labels, dtype=torch.long)

        def __len__(self) -> int:
            return len(self.labels)

        def __getitem__(self, idx: int) -> dict:
            item = {k: v[idx] for k, v in self.encodings.items()}
            item["labels"] = self.labels[idx]
            return item

    dataset = IntentDataset(texts, labels)
    dataloader = DataLoader(dataset, batch_size=16, shuffle=True)

    # 加载模型
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(INTENT_LABELS),
        id2label={i: label for i, label in enumerate(INTENT_LABELS)},
        label2id={label: i for i, label in enumerate(INTENT_LABELS)},
    )

    # 微调
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)
    model.train()

    epochs = 10
    for epoch in range(epochs):
        total_loss = 0.0
        for batch in dataloader:
            outputs = model(**batch)
            loss = outputs.loss
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            total_loss += loss.item()
        avg_loss = total_loss / len(dataloader)
        if (epoch + 1) % 3 == 0:
            print(f"  Epoch {epoch + 1}/{epochs}, Loss: {avg_loss:.4f}")

    model.eval()

    # 保存 tokenizer
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer.save_pretrained(str(output_dir))

    # 导出 ONNX
    print("📤 导出 ONNX 模型...")
    dummy_input = tokenizer(
        "你好",
        truncation=True,
        padding="max_length",
        max_length=128,
        return_tensors="pt",
    )

    onnx_path = output_dir / "intent_model.onnx"
    torch.onnx.export(
        model,
        (
            dummy_input["input_ids"],
            dummy_input["attention_mask"],
        ),
        str(onnx_path),
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "sequence"},
            "attention_mask": {0: "batch", 1: "sequence"},
            "logits": {0: "batch"},
        },
        opset_version=14,
    )

    # 保存标签
    labels_path = output_dir / "labels.json"
    labels_path.write_text(
        json.dumps(INTENT_LABELS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 保存元信息
    meta = {
        "model_type": "bert_onnx",
        "base_model": model_name,
        "num_labels": len(INTENT_LABELS),
        "labels": INTENT_LABELS,
        "training_samples": len(texts),
        "max_length": 128,
    }
    meta_path = output_dir / "model_meta.json"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n✅ ONNX 模型已保存到: {onnx_path}")
    print(f"   Tokenizer: {output_dir / 'tokenizer.json'}")
    print(f"   标签文件: {labels_path}")


def verify_model(output_dir: Path) -> bool:
    """验证模型是否可用"""
    onnx_path = output_dir / "intent_model.onnx"
    tokenizer_path = output_dir / "tokenizer.json"
    labels_path = output_dir / "labels.json"
    joblib_path = output_dir / "intent_model.joblib"

    # 检查 ONNX 模型
    if onnx_path.exists() and tokenizer_path.exists():
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            session = ort.InferenceSession(str(onnx_path))
            tokenizer_obj = Tokenizer.from_file(str(tokenizer_path))
            labels = json.loads(labels_path.read_text(encoding="utf-8"))

            # 测试推理
            encoding = tokenizer_obj.encode("你好")
            input_ids = [encoding.ids]
            attention_mask = [[1] * len(encoding.ids)]

            input_name = session.get_inputs()[0].name
            inputs = {input_name: input_ids}
            if len(session.get_inputs()) > 1:
                mask_name = session.get_inputs()[1].name
                inputs[mask_name] = attention_mask

            outputs = session.run(None, inputs)
            import numpy as np
            probs = np.exp(outputs[0][0]) / np.exp(outputs[0][0]).sum()
            best_idx = int(np.argmax(probs))

            print(f"✅ ONNX 模型验证通过")
            print(f"   测试输入: '你好'")
            print(f"   预测意图: {labels[best_idx]} (置信度: {probs[best_idx]:.2%})")
            return True

        except Exception as e:
            print(f"⚠️ ONNX 模型验证失败: {e}")
            return False

    # 检查 sklearn 模型
    if joblib_path.exists():
        try:
            import joblib
            pipeline = joblib.load(joblib_path)
            pred = pipeline.predict(["你好"])[0]
            labels = json.loads(labels_path.read_text(encoding="utf-8"))

            print(f"✅ sklearn 模型验证通过")
            print(f"   测试输入: '你好'")
            print(f"   预测意图: {labels[pred]}")
            return True

        except Exception as e:
            print(f"⚠️ sklearn 模型验证失败: {e}")
            return False

    print(f"❌ 未找到模型文件: {output_dir}")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YuanBot 意图分类模型下载/训练工具",
    )
    parser.add_argument(
        "--output", "-o",
        default="models",
        help="模型输出目录 (默认: models/)",
    )
    parser.add_argument(
        "--method", "-m",
        choices=["sklearn", "transformers"],
        default="sklearn",
        help="模型训练方式: sklearn (轻量) 或 transformers (BERT 微调)",
    )
    parser.add_argument(
        "--base-model", "-b",
        default="bert-base-chinese",
        help="HuggingFace 预训练模型名 (仅 transformers 方式)",
    )
    parser.add_argument(
        "--verify", "-v",
        action="store_true",
        help="验证已有模型是否可用",
    )

    args = parser.parse_args()
    output_dir = Path(args.output)

    if args.verify:
        verify_model(output_dir)
        return

    print("🌸 YuanBot 意图分类模型训练工具")
    print("=" * 50)

    if args.method == "sklearn":
        create_model_with_sklearn(output_dir)
    else:
        create_model_with_transformers(output_dir, args.base_model)

    print("\n🔍 验证模型...")
    verify_model(output_dir)


if __name__ == "__main__":
    main()
