"""
Train a lightweight deep neural model (from scratch with NumPy) for behavior scoring.
This script demonstrates a deep-learning style workflow without heavy external frameworks.
"""
import json
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = BASE_DIR / "artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def build_synthetic_data(n=1200, seed=42):
    rng = np.random.default_rng(seed)
    features = rng.normal(0, 1, (n, 6))
    weights = np.array([0.8, 1.2, 1.4, 0.9, -0.7, -0.4])
    logits = features @ weights + rng.normal(0, 0.5, n)
    labels = (sigmoid(logits) > 0.5).astype(np.float32).reshape(-1, 1)
    return features.astype(np.float32), labels


def train():
    x, y = build_synthetic_data()
    n_samples, input_dim = x.shape
    hidden_dim = 12

    rng = np.random.default_rng(123)
    w1 = rng.normal(0, 0.1, (input_dim, hidden_dim)).astype(np.float32)
    b1 = np.zeros((1, hidden_dim), dtype=np.float32)
    w2 = rng.normal(0, 0.1, (hidden_dim, 1)).astype(np.float32)
    b2 = np.zeros((1, 1), dtype=np.float32)

    lr = 0.02
    epochs = 300

    for epoch in range(epochs):
        z1 = x @ w1 + b1
        a1 = np.maximum(0, z1)
        z2 = a1 @ w2 + b2
        y_pred = sigmoid(z2)

        eps = 1e-7
        loss = -np.mean(y * np.log(y_pred + eps) + (1 - y) * np.log(1 - y_pred + eps))

        dz2 = (y_pred - y) / n_samples
        dw2 = a1.T @ dz2
        db2 = np.sum(dz2, axis=0, keepdims=True)
        da1 = dz2 @ w2.T
        dz1 = da1 * (z1 > 0)
        dw1 = x.T @ dz1
        db1 = np.sum(dz1, axis=0, keepdims=True)

        w1 -= lr * dw1
        b1 -= lr * db1
        w2 -= lr * dw2
        b2 -= lr * db2

        if epoch % 50 == 0:
            preds = (y_pred > 0.5).astype(np.float32)
            acc = float((preds == y).mean())
            print(f"epoch={epoch:03d} loss={loss:.4f} acc={acc:.4f}")

    artifact = {
        "input_dim": input_dim,
        "hidden_dim": hidden_dim,
        "w1": w1.tolist(),
        "b1": b1.tolist(),
        "w2": w2.tolist(),
        "b2": b2.tolist(),
    }
    target = ARTIFACT_DIR / "model_behavior.json"
    target.write_text(json.dumps(artifact), encoding="utf-8")
    print(f"Saved artifact to: {target}")


if __name__ == "__main__":
    train()
