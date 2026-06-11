import argparse
import csv
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data_pipeline.schema import ACTIONS
from model_behavior.next_item import ModelConfig, build_model


ACTION_TO_INDEX = {action: index + 1 for index, action in enumerate(ACTIONS)}


def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    import torch

    torch.manual_seed(seed)


def read_rows(path):
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows.sort(key=lambda row: (row["user_id"], row["timestamp"]))
    return rows


def build_vocab(rows, max_items=5000):
    counts = Counter(row["item_id"] for row in rows)
    selected = [item for item, _ in counts.most_common(max_items)]
    return {item: index + 1 for index, item in enumerate(selected)}


def build_sequences(rows, item_to_index, sequence_length=10):
    grouped = defaultdict(list)
    for row in rows:
        if row["item_id"] in item_to_index:
            grouped[row["user_id"]].append(row)

    samples = []
    for events in grouped.values():
        events.sort(key=lambda row: row["timestamp"])
        for target_index in range(1, len(events)):
            context = events[max(0, target_index - sequence_length) : target_index]
            target = events[target_index]
            if target["item_id"] not in item_to_index:
                continue
            items = [item_to_index[row["item_id"]] for row in context]
            actions = [ACTION_TO_INDEX[row["action"]] for row in context]
            timestamps = [
                datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                for row in context
            ]
            deltas = [0.0]
            for left, right in zip(timestamps, timestamps[1:]):
                hours = max(0.0, (right - left).total_seconds() / 3600)
                deltas.append(min(math.log1p(hours) / 10, 1.0))
            padding = sequence_length - len(items)
            samples.append(
                (
                    [0] * padding + items,
                    [0] * padding + actions,
                    [0.0] * padding + deltas,
                    item_to_index[target["item_id"]] - 1,
                    ACTION_TO_INDEX[target["action"]] - 1,
                )
            )
    return samples


def build_evaluation_sequences(
    history_rows, target_rows, item_to_index, sequence_length=10
):
    history = defaultdict(list)
    targets = defaultdict(list)
    for row in history_rows:
        if row["item_id"] in item_to_index:
            history[row["user_id"]].append(row)
    for row in target_rows:
        if row["item_id"] in item_to_index:
            targets[row["user_id"]].append(row)

    samples = []
    for user_id, user_targets in targets.items():
        context = sorted(history.get(user_id, []), key=lambda row: row["timestamp"])
        for target in sorted(user_targets, key=lambda row: row["timestamp"]):
            window = context[-sequence_length:]
            if window:
                items = [item_to_index[row["item_id"]] for row in window]
                actions = [ACTION_TO_INDEX[row["action"]] for row in window]
                timestamps = [
                    datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                    for row in window
                ]
                deltas = [0.0]
                for left, right in zip(timestamps, timestamps[1:]):
                    hours = max(0.0, (right - left).total_seconds() / 3600)
                    deltas.append(min(math.log1p(hours) / 10, 1.0))
                padding = sequence_length - len(items)
                samples.append(
                    (
                        [0] * padding + items,
                        [0] * padding + actions,
                        [0.0] * padding + deltas,
                        item_to_index[target["item_id"]] - 1,
                        ACTION_TO_INDEX[target["action"]] - 1,
                    )
                )
            context.append(target)
    return samples


def batches(samples, batch_size, shuffle=False):
    import torch

    indices = list(range(len(samples)))
    if shuffle:
        random.shuffle(indices)
    for start in range(0, len(indices), batch_size):
        selected = [samples[index] for index in indices[start : start + batch_size]]
        yield (
            torch.LongTensor([sample[0] for sample in selected]),
            torch.LongTensor([sample[1] for sample in selected]),
            torch.FloatTensor([sample[2] for sample in selected]),
            torch.LongTensor([sample[3] for sample in selected]),
            torch.LongTensor([sample[4] for sample in selected]),
        )


def ranking_metrics(ranked, target, k_values=(5, 10)):
    metrics = {f"recall@{k}": 0.0 for k in k_values}
    metrics["mrr@10"] = 0.0
    metrics["ndcg@10"] = 0.0
    if target in ranked[:10]:
        rank = ranked.index(target) + 1
        metrics["mrr@10"] = 1 / rank
        metrics["ndcg@10"] = 1 / math.log2(rank + 1)
    for k in k_values:
        metrics[f"recall@{k}"] = float(target in ranked[:k])
    return metrics


def evaluate(model, samples, batch_size=256):
    import torch

    totals = Counter()
    action_true = []
    action_pred = []
    model.eval()
    with torch.no_grad():
        for items, actions, deltas, targets, action_targets in batches(
            samples, batch_size
        ):
            item_logits, action_logits = model(items, actions, deltas)
            top = torch.topk(item_logits, min(10, item_logits.shape[1]), dim=1).indices
            for ranked, target in zip(top.tolist(), targets.tolist()):
                totals.update(ranking_metrics(ranked, target))
                totals["count"] += 1
            action_true.extend(action_targets.tolist())
            action_pred.extend(action_logits.argmax(dim=1).tolist())
    count = max(1, totals["count"])
    result = {
        key: round(totals[key] / count, 6)
        for key in ("recall@5", "recall@10", "mrr@10", "ndcg@10")
    }
    correct = sum(a == b for a, b in zip(action_true, action_pred))
    result["action_accuracy"] = round(correct / max(1, len(action_true)), 6)
    f1_values = []
    for label in range(len(ACTIONS)):
        tp = sum(t == label and p == label for t, p in zip(action_true, action_pred))
        fp = sum(t != label and p == label for t, p in zip(action_true, action_pred))
        fn = sum(t == label and p != label for t, p in zip(action_true, action_pred))
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        f1_values.append(
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0
        )
    result["action_macro_f1"] = round(sum(f1_values) / len(f1_values), 6)
    return result


def popularity_metrics(train_rows, validation_rows, item_to_index):
    popular = [
        item_to_index[item] - 1
        for item, _ in Counter(row["item_id"] for row in train_rows).most_common(10)
        if item in item_to_index
    ]
    values = Counter()
    count = 0
    for row in validation_rows:
        if row["item_id"] not in item_to_index:
            continue
        values.update(ranking_metrics(popular, item_to_index[row["item_id"]] - 1))
        count += 1
    return {
        key: round(values[key] / max(1, count), 6)
        for key in ("recall@5", "recall@10", "mrr@10", "ndcg@10")
    }


def train_domain(domain_dir, artifact_root, epochs=5, batch_size=128):
    import torch
    import torch.nn as nn

    domain_dir = Path(domain_dir)
    train_rows = read_rows(domain_dir / "train.csv")
    validation_rows = read_rows(domain_dir / "validation.csv")
    test_rows = read_rows(domain_dir / "test.csv")
    if not train_rows:
        raise ValueError(f"No training data in {domain_dir}")
    domain = train_rows[0]["domain"]
    source = train_rows[0]["source"]
    item_to_index = build_vocab(train_rows)
    config = ModelConfig(
        item_count=len(item_to_index),
        action_count=len(ACTIONS),
    )
    train_samples = build_sequences(train_rows, item_to_index, config.sequence_length)
    validation_samples = build_evaluation_sequences(
        train_rows, validation_rows, item_to_index, config.sequence_length
    )
    test_samples = build_evaluation_sequences(
        train_rows + validation_rows, test_rows, item_to_index, config.sequence_length
    )
    if not train_samples:
        raise ValueError(f"Not enough sequential interactions for {domain}")

    comparison = {}
    trained = {}
    for architecture in ("SimpleRNN", "LSTM", "BiLSTM"):
        model = build_model(architecture, config)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.002)
        item_loss = nn.CrossEntropyLoss()
        action_loss = nn.CrossEntropyLoss()
        for _ in range(epochs):
            model.train()
            for items, actions, deltas, targets, action_targets in batches(
                train_samples, batch_size, shuffle=True
            ):
                optimizer.zero_grad()
                item_logits, action_logits = model(items, actions, deltas)
                loss = item_loss(item_logits, targets) + 0.2 * action_loss(
                    action_logits, action_targets
                )
                loss.backward()
                optimizer.step()
        comparison[architecture] = evaluate(model, validation_samples)
        trained[architecture] = model

    best_name = max(comparison, key=lambda name: comparison[name]["ndcg@10"])
    best_model = trained[best_name]
    version = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    artifact_root = Path(artifact_root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_name = f"{domain}-{version}.pt"
    torch.save(
        {
            "architecture": best_name,
            "model_state_dict": best_model.state_dict(),
            "config": config.__dict__,
            "item_to_index": item_to_index,
            "index_to_item": {
                str(index): item for item, index in item_to_index.items()
            },
            "action_to_index": ACTION_TO_INDEX,
            "source": source,
            "domain": domain,
            "metrics": comparison[best_name],
        },
        artifact_root / artifact_name,
    )
    report = {
        "domain": domain,
        "source": source,
        "version": version,
        "artifact": artifact_name,
        "best_model": best_name,
        "validation": comparison,
        "test": evaluate(best_model, test_samples),
        "popularity_baseline": popularity_metrics(
            train_rows, validation_rows, item_to_index
        ),
        "sample_counts": {
            "train": len(train_samples),
            "validation": len(validation_samples),
            "test": len(test_samples),
        },
    }
    (artifact_root / f"{domain}-{version}.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--processed-root", default=str(BASE_DIR / "data" / "processed")
    )
    parser.add_argument(
        "--artifact-root", default=str(BASE_DIR / "model_behavior" / "artifacts")
    )
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()
    set_seed()

    reports = []
    root = Path(args.processed_root)
    for domain in ("book", "electronics", "fashion"):
        reports.append(
            train_domain(
                root / domain,
                args.artifact_root,
                epochs=args.epochs,
                batch_size=args.batch_size,
            )
        )
    registry = {
        "version": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
        "acceptance": {},
        "domains": {
            report["domain"]: {
                "artifact": report["artifact"],
                "version": report["version"],
                "source": report["source"],
                "metrics": report["test"],
            }
            for report in reports
        },
    }
    registry_path = Path(args.artifact_root) / "registry.json"
    comparisons = [
        {
            "domain": report["domain"],
            "model_ndcg@10": report["validation"][report["best_model"]]["ndcg@10"],
            "baseline_ndcg@10": report["popularity_baseline"]["ndcg@10"],
        }
        for report in reports
    ]
    passed_domains = sum(
        item["model_ndcg@10"] > item["baseline_ndcg@10"]
        for item in comparisons
    )
    within_tolerance = all(
        item["model_ndcg@10"] >= item["baseline_ndcg@10"] * 0.95
        for item in comparisons
    )
    registry["acceptance"] = {
        "passed": passed_domains >= 2 and within_tolerance,
        "passed_domains": passed_domains,
        "required_domains": 2,
        "remaining_domains_within_five_percent": within_tolerance,
        "comparisons": comparisons,
    }
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    print(json.dumps({"registry": registry, "reports": reports}, indent=2))


if __name__ == "__main__":
    main()
