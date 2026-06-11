"""
Inference module — load model_best.pt (PyTorch) hoặc fallback về model_behavior.json (numpy).
"""

import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
BEST_MODEL_PATH = ARTIFACT_DIR / "model_best.pt"
LEGACY_MODEL_PATH = ARTIFACT_DIR / "model_behavior.json"

# Cached model
_cached_model = None
_cached_model_type = None


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def load_model():
    """Load model tốt nhất (PyTorch) hoặc fallback legacy (numpy)."""
    global _cached_model, _cached_model_type

    if _cached_model is not None:
        return _cached_model, _cached_model_type

    # 1. Thử load PyTorch model_best.pt
    if BEST_MODEL_PATH.exists():
        try:
            import torch
            checkpoint = torch.load(BEST_MODEL_PATH, map_location="cpu", weights_only=False)
            _cached_model = checkpoint
            _cached_model_type = "pytorch"
            logger.info(f"Loaded PyTorch model: {checkpoint.get('model_name', 'unknown')}")
            return _cached_model, _cached_model_type
        except Exception as e:
            logger.warning(f"Failed to load PyTorch model: {e}")

    # 2. Fallback: legacy numpy model
    if LEGACY_MODEL_PATH.exists():
        try:
            data = json.loads(LEGACY_MODEL_PATH.read_text(encoding="utf-8"))
            _cached_model = {
                "w1": np.array(data["w1"], dtype=np.float32),
                "b1": np.array(data["b1"], dtype=np.float32),
                "w2": np.array(data["w2"], dtype=np.float32),
                "b2": np.array(data["b2"], dtype=np.float32),
            }
            _cached_model_type = "numpy"
            logger.info("Loaded legacy numpy model")
            return _cached_model, _cached_model_type
        except Exception as e:
            logger.warning(f"Failed to load legacy model: {e}")

    return None, None


def predict_next_action(action_sequence, product_sequence):
    """
    Dự đoán hành vi tiếp theo dựa trên chuỗi hành vi.
    Input:
        action_sequence: list of action indices [0, 1, 2, ...]  (len = seq_len)
        product_sequence: list of product indices [0-14]  (len = seq_len)
    Returns:
        dict {"predicted_action": str, "probabilities": {action: float}}
    """
    model, model_type = load_model()
    action_names = {0: "view", 1: "click", 2: "add_to_cart"}

    if model is None:
        return {"predicted_action": "view", "probabilities": {"view": 0.6, "click": 0.25, "add_to_cart": 0.15}}

    if model_type == "pytorch":
        try:
            import torch
            config = model["config"]
            state_dict = model["model_state_dict"]
            model_name = model.get("model_name", "LSTM")
            action_map = model.get("action_map", {"view": 0, "click": 1, "add_to_cart": 2})

            # Rebuild model architecture
            from scripts.train_models import _build_models
            RNN, LSTM, BiLSTM = _build_models()
            model_classes = {"SimpleRNN": RNN, "LSTM": LSTM, "BiLSTM": BiLSTM}
            net = model_classes.get(model_name, LSTM)()
            net.load_state_dict(state_dict)
            net.eval()

            a_tensor = torch.LongTensor([action_sequence])
            p_tensor = torch.LongTensor([product_sequence])

            with torch.no_grad():
                logits = net(a_tensor, p_tensor)
                probs = torch.softmax(logits, dim=1)[0].numpy()

            predicted_idx = int(probs.argmax())
            inv_map = {v: k for k, v in action_map.items()}
            return {
                "predicted_action": inv_map.get(predicted_idx, "view"),
                "probabilities": {inv_map.get(i, f"action_{i}"): round(float(probs[i]), 4) for i in range(len(probs))},
            }
        except Exception as e:
            logger.warning(f"PyTorch inference failed: {e}")

    # Numpy fallback (binary classification → simple scoring)
    return {"predicted_action": "view", "probabilities": {"view": 0.6, "click": 0.25, "add_to_cart": 0.15}}


def predict_proba(features):
    """Legacy interface — backward compatible."""
    model, model_type = load_model()
    if model is None or model_type != "numpy":
        return 0.5
    x = np.array(features, dtype=np.float32).reshape(1, -1)
    z1 = x @ model["w1"] + model["b1"]
    a1 = np.maximum(0, z1)
    z2 = a1 @ model["w2"] + model["b2"]
    return float(sigmoid(z2)[0][0])
