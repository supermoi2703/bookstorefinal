import importlib.util
import csv
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec("torch"), "PyTorch is not installed")
class NextItemModelTests(unittest.TestCase):
    def test_all_architectures_produce_item_and_action_logits(self):
        import torch

        from model_behavior.next_item import ModelConfig, build_model

        config = ModelConfig(
            item_count=20,
            action_count=6,
            embedding_dim=8,
            hidden_dim=12,
            sequence_length=5,
        )
        items = torch.randint(0, 20, (2, 5))
        actions = torch.randint(0, 6, (2, 5))
        deltas = torch.zeros((2, 5))
        for architecture in ("SimpleRNN", "LSTM", "BiLSTM"):
            item_logits, action_logits = build_model(architecture, config)(
                items, actions, deltas
            )
            self.assertEqual(tuple(item_logits.shape), (2, 20))
            self.assertEqual(tuple(action_logits.shape), (2, 6))

    def test_training_smoke_creates_next_item_artifact(self):
        from scripts.train_next_item import train_domain

        with tempfile.TemporaryDirectory() as tmp:
            domain_dir = Path(tmp) / "book"
            artifact_dir = Path(tmp) / "artifacts"
            domain_dir.mkdir()
            fields = [
                "source",
                "domain",
                "user_id",
                "item_id",
                "action",
                "timestamp",
                "rating",
            ]
            splits = {"train.csv": [], "validation.csv": [], "test.csv": []}
            for user in range(5):
                for event in range(6):
                    row = {
                        "source": "goodreads",
                        "domain": "book",
                        "user_id": f"u{user}",
                        "item_id": f"p{(user + event) % 5}",
                        "action": "READ",
                        "timestamp": f"2025-01-{event + 1:02d}T00:00:00+00:00",
                        "rating": "4",
                    }
                    target = (
                        "train.csv"
                        if event < 4
                        else "validation.csv"
                        if event == 4
                        else "test.csv"
                    )
                    splits[target].append(row)
            for name, rows in splits.items():
                with (domain_dir / name).open(
                    "w", encoding="utf-8", newline=""
                ) as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
            report = train_domain(
                domain_dir, artifact_dir, epochs=1, batch_size=8
            )
            self.assertIn(report["best_model"], {"SimpleRNN", "LSTM", "BiLSTM"})
            self.assertTrue((artifact_dir / report["artifact"]).exists())
            self.assertIn("ndcg@10", report["test"])
