"""
Câu 2a: Xây dựng 3 mô hình RNN, LSTM, biLSTM
- Dự đoán next action (view / click / add_to_cart) dựa trên chuỗi hành vi user
- So sánh accuracy, precision, recall, F1 ⟹ chọn model_best
- Lưu plots + model_best.pt
"""

import csv
import os
import json
import random
from pathlib import Path
from collections import defaultdict

import numpy as np

# ============================================================
# Cấu hình đường dẫn
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "data_user500.csv"
PLOTS_DIR = BASE_DIR / "plots"
ARTIFACT_DIR = BASE_DIR / "model_behavior" / "artifacts"

PLOTS_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# Hyperparameters
# ============================================================
ACTION_MAP = {"view": 0, "click": 1, "add_to_cart": 2}
NUM_ACTIONS = len(ACTION_MAP)
EMBED_DIM = 16
HIDDEN_DIM = 32
SEQ_LEN = 5            # Dùng 5 hành vi liên tiếp để dự đoán hành vi thứ 6
NUM_PRODUCTS = 15
LEARNING_RATE = 0.003
EPOCHS = 40
BATCH_SIZE = 64
SEED = 42

# ============================================================
# Hàm tiện ích
# ============================================================

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
    except ImportError:
        pass


def load_data():
    """Đọc CSV và nhóm theo user_id."""
    user_sequences = defaultdict(list)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = int(row["user_id"])
            pid = int(row["product_id"])
            action = row["action"]
            user_sequences[uid].append({"product_id": pid, "action": action})
    return user_sequences


def build_sequences(user_sequences, seq_len=SEQ_LEN):
    """Tạo chuỗi input-output cho bài toán next-action prediction."""
    X_action = []
    X_product = []
    y = []
    for uid, events in user_sequences.items():
        if len(events) <= seq_len:
            continue
        for i in range(len(events) - seq_len):
            seq = events[i : i + seq_len]
            target = events[i + seq_len]

            actions = [ACTION_MAP[e["action"]] for e in seq]
            products = [e["product_id"] - 1 for e in seq]  # 0-indexed
            label = ACTION_MAP[target["action"]]

            X_action.append(actions)
            X_product.append(products)
            y.append(label)

    X_action = np.array(X_action, dtype=np.int64)
    X_product = np.array(X_product, dtype=np.int64)
    y = np.array(y, dtype=np.int64)
    return X_action, X_product, y


def train_test_split(X_action, X_product, y, test_ratio=0.2):
    n = len(y)
    indices = np.arange(n)
    np.random.shuffle(indices)
    split = int(n * (1 - test_ratio))
    train_idx, test_idx = indices[:split], indices[split:]
    return (
        X_action[train_idx], X_product[train_idx], y[train_idx],
        X_action[test_idx], X_product[test_idx], y[test_idx],
    )


# ============================================================
# PyTorch Models
# ============================================================

def _build_models():
    """Import torch và định nghĩa 3 mô hình."""
    import torch
    import torch.nn as nn

    class BehaviorRNN(nn.Module):
        """Simple RNN model."""
        def __init__(self):
            super().__init__()
            self.action_emb = nn.Embedding(NUM_ACTIONS, EMBED_DIM)
            self.product_emb = nn.Embedding(NUM_PRODUCTS, EMBED_DIM)
            self.rnn = nn.RNN(EMBED_DIM * 2, HIDDEN_DIM, batch_first=True)
            self.fc = nn.Linear(HIDDEN_DIM, NUM_ACTIONS)
            self.dropout = nn.Dropout(0.2)

        def forward(self, action_seq, product_seq):
            a = self.action_emb(action_seq)
            p = self.product_emb(product_seq)
            x = torch.cat([a, p], dim=-1)
            out, _ = self.rnn(x)
            out = self.dropout(out[:, -1, :])
            return self.fc(out)

    class BehaviorLSTM(nn.Module):
        """LSTM model."""
        def __init__(self):
            super().__init__()
            self.action_emb = nn.Embedding(NUM_ACTIONS, EMBED_DIM)
            self.product_emb = nn.Embedding(NUM_PRODUCTS, EMBED_DIM)
            self.lstm = nn.LSTM(EMBED_DIM * 2, HIDDEN_DIM, batch_first=True)
            self.fc = nn.Linear(HIDDEN_DIM, NUM_ACTIONS)
            self.dropout = nn.Dropout(0.2)

        def forward(self, action_seq, product_seq):
            a = self.action_emb(action_seq)
            p = self.product_emb(product_seq)
            x = torch.cat([a, p], dim=-1)
            out, _ = self.lstm(x)
            out = self.dropout(out[:, -1, :])
            return self.fc(out)

    class BehaviorBiLSTM(nn.Module):
        """Bidirectional LSTM model."""
        def __init__(self):
            super().__init__()
            self.action_emb = nn.Embedding(NUM_ACTIONS, EMBED_DIM)
            self.product_emb = nn.Embedding(NUM_PRODUCTS, EMBED_DIM)
            self.bilstm = nn.LSTM(
                EMBED_DIM * 2, HIDDEN_DIM, batch_first=True, bidirectional=True
            )
            self.fc = nn.Linear(HIDDEN_DIM * 2, NUM_ACTIONS)
            self.dropout = nn.Dropout(0.2)

        def forward(self, action_seq, product_seq):
            a = self.action_emb(action_seq)
            p = self.product_emb(product_seq)
            x = torch.cat([a, p], dim=-1)
            out, _ = self.bilstm(x)
            out = self.dropout(out[:, -1, :])
            return self.fc(out)

    return BehaviorRNN, BehaviorLSTM, BehaviorBiLSTM


# ============================================================
# Training loop
# ============================================================

def train_one_model(model, train_data, val_data, model_name, epochs=EPOCHS):
    import torch
    import torch.nn as nn
    X_a_train, X_p_train, y_train = train_data
    X_a_val, X_p_val, y_val = val_data
    # Chuyển sang tensor
    X_a_train_t = torch.LongTensor(X_a_train)
    X_p_train_t = torch.LongTensor(X_p_train)
    y_train_t = torch.LongTensor(y_train)
    X_a_val_t = torch.LongTensor(X_a_val)
    X_p_val_t = torch.LongTensor(X_p_val)
    y_val_t = torch.LongTensor(y_val)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    history = {"train_loss": [], "val_loss": [], "train_acc": [], "val_acc": []}
    n_train = len(y_train)
    for epoch in range(epochs):
        model.train()
        # Shuffle
        perm = torch.randperm(n_train)
        epoch_loss = 0.0
        correct = 0
        total = 0
        for start in range(0, n_train, BATCH_SIZE):
            idx = perm[start : start + BATCH_SIZE]
            a_batch = X_a_train_t[idx]
            p_batch = X_p_train_t[idx]
            y_batch = y_train_t[idx]
            optimizer.zero_grad()
            logits = model(a_batch, p_batch)
            loss = criterion(logits, y_batch)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * len(idx)
            preds = logits.argmax(dim=1)
            correct += (preds == y_batch).sum().item()
            total += len(idx)
        train_loss = epoch_loss / total
        train_acc = correct / total
        # Validation
        model.eval()
        with torch.no_grad():
            val_logits = model(X_a_val_t, X_p_val_t)
            val_loss = criterion(val_logits, y_val_t).item()
            val_preds = val_logits.argmax(dim=1)
            val_acc = (val_preds == y_val_t).float().mean().item()
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["train_acc"].append(train_acc)
        history["val_acc"].append(val_acc)

        if (epoch + 1) % 10 == 0 or epoch == 0:
            print(
                f"  [{model_name}] Epoch {epoch+1:3d}/{epochs} "
                f"| Train Loss: {train_loss:.4f} Acc: {train_acc:.4f} "
                f"| Val Loss: {val_loss:.4f} Acc: {val_acc:.4f}"
            )
    # Final preds cho evaluation
    model.eval()
    with torch.no_grad():
        final_preds = model(X_a_val_t, X_p_val_t).argmax(dim=1).numpy()

    return history, final_preds


# ============================================================
# Metrics
# ============================================================

def compute_metrics(y_true, y_pred, class_names):
    """Tính accuracy, precision, recall, F1 cho mỗi class."""
    from collections import Counter
    n = len(y_true)
    accuracy = np.mean(y_true == y_pred)

    results = {"accuracy": accuracy, "classes": {}}
    for i, name in enumerate(class_names):
        tp = np.sum((y_pred == i) & (y_true == i))
        fp = np.sum((y_pred == i) & (y_true != i))
        fn = np.sum((y_pred != i) & (y_true == i))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        results["classes"][name] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    # Macro avg
    precisions = [v["precision"] for v in results["classes"].values()]
    recalls = [v["recall"] for v in results["classes"].values()]
    f1s = [v["f1"] for v in results["classes"].values()]
    results["macro_precision"] = round(np.mean(precisions), 4)
    results["macro_recall"] = round(np.mean(recalls), 4)
    results["macro_f1"] = round(np.mean(f1s), 4)
    results["accuracy"] = round(accuracy, 4)

    return results


def confusion_matrix(y_true, y_pred, num_classes):
    cm = np.zeros((num_classes, num_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[t][p] += 1
    return cm


# ============================================================
# Plotting (matplotlib)
# ============================================================

def plot_training_curves(all_histories, save_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Loss curves
    for name, h in all_histories.items():
        axes[0].plot(h["train_loss"], label=f"{name} (train)", linestyle="-")
        axes[0].plot(h["val_loss"], label=f"{name} (val)", linestyle="--")
    axes[0].set_title("Training / Validation Loss", fontweight="bold")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)

    # Accuracy curves
    for name, h in all_histories.items():
        axes[1].plot(h["train_acc"], label=f"{name} (train)", linestyle="-")
        axes[1].plot(h["val_acc"], label=f"{name} (val)", linestyle="--")
    axes[1].set_title("Training / Validation Accuracy", fontweight="bold")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Accuracy")
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_dir / "training_curves.png", dpi=150)
    plt.close()
    print(f"  Saved: {save_dir / 'training_curves.png'}")


def plot_accuracy_comparison(all_metrics, save_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = list(all_metrics.keys())
    accuracies = [all_metrics[n]["accuracy"] for n in names]
    f1_scores = [all_metrics[n]["macro_f1"] for n in names]

    x = np.arange(len(names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    bars1 = ax.bar(x - width / 2, accuracies, width, label="Accuracy", color="#22c55e", alpha=0.85)
    bars2 = ax.bar(x + width / 2, f1_scores, width, label="Macro F1", color="#3b82f6", alpha=0.85)

    ax.set_ylabel("Score")
    ax.set_title("Model Comparison: Accuracy & F1", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.legend()
    ax.set_ylim(0, 1.1)
    ax.grid(axis="y", alpha=0.3)

    # Ghi giá trị lên bar
    for bar in bars1:
        ax.annotate(f"{bar.get_height():.3f}", xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    xytext=(0, 4), textcoords="offset points", ha="center", fontsize=9, fontweight="bold")
    for bar in bars2:
        ax.annotate(f"{bar.get_height():.3f}", xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    xytext=(0, 4), textcoords="offset points", ha="center", fontsize=9, fontweight="bold")

    plt.tight_layout()
    plt.savefig(save_dir / "accuracy_comparison.png", dpi=150)
    plt.close()
    print(f"  Saved: {save_dir / 'accuracy_comparison.png'}")


def plot_confusion_matrix(cm, class_names, model_name, save_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm, interpolation="nearest", cmap="Greens")
    ax.figure.colorbar(im, ax=ax)
    ax.set(
        xticks=np.arange(cm.shape[1]),
        yticks=np.arange(cm.shape[0]),
        xticklabels=class_names,
        yticklabels=class_names,
        title=f"Confusion Matrix — {model_name}",
        ylabel="True label",
        xlabel="Predicted label",
    )
    ax.title.set_fontweight("bold")

    # Ghi số vào ô
    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, format(cm[i, j], "d"),
                    ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black",
                    fontweight="bold")

    plt.tight_layout()
    fname = f"confusion_{model_name.lower().replace(' ', '_').replace('-', '')}.png"
    plt.savefig(save_dir / fname, dpi=150)
    plt.close()
    print(f"  Saved: {save_dir / fname}")


# ============================================================
# Main
# ============================================================

def main():
    import torch

    set_seed(SEED)

    print("=" * 60)
    print("STEP 1: Loading data")
    print("=" * 60)

    if not DATA_FILE.exists():
        print(f"ERROR: {DATA_FILE} not found. Run generate_data.py first.")
        return

    user_sequences = load_data()
    print(f"  Users loaded: {len(user_sequences)}")

    X_action, X_product, y = build_sequences(user_sequences)
    print(f"  Total sequences: {len(y)}")
    print(f"  Class distribution: {dict(zip(*np.unique(y, return_counts=True)))}")

    X_a_train, X_p_train, y_train, X_a_val, X_p_val, y_val = train_test_split(
        X_action, X_product, y, test_ratio=0.2
    )
    print(f"  Train: {len(y_train)}, Val: {len(y_val)}")

    print("\n" + "=" * 60)
    print("STEP 2: Training 3 models")
    print("=" * 60)

    BehaviorRNN, BehaviorLSTM, BehaviorBiLSTM = _build_models()

    models_config = {
        "SimpleRNN": BehaviorRNN(),
        "LSTM": BehaviorLSTM(),
        "BiLSTM": BehaviorBiLSTM(),
    }

    train_data = (X_a_train, X_p_train, y_train)
    val_data = (X_a_val, X_p_val, y_val)

    all_histories = {}
    all_predictions = {}
    all_metrics = {}
    class_names = list(ACTION_MAP.keys())

    for name, model in models_config.items():
        print(f"\n--- Training {name} ---")
        param_count = sum(p.numel() for p in model.parameters())
        print(f"  Parameters: {param_count:,}")

        history, preds = train_one_model(model, train_data, val_data, name)
        all_histories[name] = history
        all_predictions[name] = preds

        metrics = compute_metrics(y_val, preds, class_names)
        all_metrics[name] = metrics

        cm = confusion_matrix(y_val, preds, NUM_ACTIONS)
        plot_confusion_matrix(cm, class_names, name, PLOTS_DIR)

    print("\n" + "=" * 60)
    print("STEP 3: Model Comparison")
    print("=" * 60)

    print(f"\n{'Model':<12} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    print("-" * 55)
    for name, m in all_metrics.items():
        print(f"{name:<12} {m['accuracy']:>10.4f} {m['macro_precision']:>10.4f} "
              f"{m['macro_recall']:>10.4f} {m['macro_f1']:>10.4f}")

    # Chọn model tốt nhất theo macro_f1
    best_name = max(all_metrics, key=lambda n: all_metrics[n]["macro_f1"])
    best_model = models_config[best_name]
    print(f"\n  [BEST] Best model: {best_name} (F1 = {all_metrics[best_name]['macro_f1']:.4f})")

    print("\n" + "=" * 60)
    print("STEP 4: Saving artifacts")
    print("=" * 60)

    # Plot training curves
    plot_training_curves(all_histories, PLOTS_DIR)
    plot_accuracy_comparison(all_metrics, PLOTS_DIR)

    # Save best model
    model_path = ARTIFACT_DIR / "model_best.pt"
    torch.save({
        "model_name": best_name,
        "model_state_dict": best_model.state_dict(),
        "config": {
            "num_actions": NUM_ACTIONS,
            "num_products": NUM_PRODUCTS,
            "embed_dim": EMBED_DIM,
            "hidden_dim": HIDDEN_DIM,
            "seq_len": SEQ_LEN,
        },
        "metrics": all_metrics[best_name],
        "action_map": ACTION_MAP,
    }, model_path)
    print(f"  Saved model: {model_path}")

    # Save comparison report JSON
    report = {
        "best_model": best_name,
        "comparison": all_metrics,
    }
    report_path = ARTIFACT_DIR / "training_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Saved report: {report_path}")

    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)
    print(f"  Best model  : {best_name}")
    print(f"  Accuracy    : {all_metrics[best_name]['accuracy']:.4f}")
    print(f"  Macro F1    : {all_metrics[best_name]['macro_f1']:.4f}")
    print(f"  Model file  : {model_path}")
    print(f"  Plots dir   : {PLOTS_DIR}")


if __name__ == "__main__":
    main()
