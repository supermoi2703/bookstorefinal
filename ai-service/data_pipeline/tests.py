import csv
import json
import tempfile
import unittest
from pathlib import Path

from data_pipeline.adapters import (
    AmazonElectronicsAdapter,
    GoodreadsAdapter,
    HMFashionAdapter,
)
from data_pipeline.pipeline import prepare_dataset
from data_pipeline.schema import normalize_action


class AdapterTests(unittest.TestCase):
    def test_action_normalization(self):
        self.assertEqual(normalize_action("add-to-cart"), "ADD_TO_CART")
        self.assertEqual(normalize_action("buy"), "PURCHASE")
        self.assertEqual(normalize_action("", rating=5), "RATE")

    def test_goodreads_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reviews.json"
            path.write_text(
                json.dumps(
                    {
                        "user_id": "u1",
                        "book_id": "b1",
                        "is_read": True,
                        "rating": 4,
                        "date_updated": "2025-01-01",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            row = next(iter(GoodreadsAdapter(str(path)).interactions()))
            self.assertEqual((row.domain, row.action, row.item_id), ("book", "READ", "b1"))

    def test_amazon_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reviews.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "user_id": "u1",
                        "parent_asin": "a1",
                        "rating": 5,
                        "timestamp": 1735689600000,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            row = next(iter(AmazonElectronicsAdapter(str(path)).interactions()))
            self.assertEqual(
                (row.domain, row.action, row.item_id), ("electronics", "RATE", "a1")
            )

    def test_hm_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transactions.csv"
            path.write_text(
                "t_dat,customer_id,article_id,price\n2025-01-01,c1,1001,0.1\n",
                encoding="utf-8",
            )
            row = next(iter(HMFashionAdapter(str(path)).interactions()))
            self.assertEqual(
                (row.domain, row.action, row.item_id), ("fashion", "PURCHASE", "1001")
            )


class PipelineTests(unittest.TestCase):
    def test_temporal_split_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            interactions = root / "transactions.csv"
            products = root / "articles.csv"
            with interactions.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["t_dat", "customer_id", "article_id", "price"],
                )
                writer.writeheader()
                for day in range(1, 31):
                    writer.writerow(
                        {
                            "t_dat": f"2025-01-{day:02d}",
                            "customer_id": f"u{day % 3}",
                            "article_id": f"p{day % 3}",
                            "price": "0.1",
                        }
                    )
            products.write_text(
                "article_id,prod_name,section_name,detail_desc\n"
                "p0,Shirt,Fashion,Cotton shirt\n"
                "p1,Trousers,Fashion,Black trousers\n"
                "p2,Shoes,Fashion,Running shoes\n",
                encoding="utf-8",
            )
            manifest = prepare_dataset(
                {
                    "adapter": "hm",
                    "interactions": str(interactions),
                    "metadata": str(products),
                    "max_interactions": 100,
                    "max_products": 10,
                    "min_interactions": 5,
                },
                root / "processed",
            )
            self.assertEqual(manifest["counts"]["interactions"], 30)
            with (root / "processed" / "fashion" / "train.csv").open(
                encoding="utf-8"
            ) as handle:
                train = list(csv.DictReader(handle))
            with (root / "processed" / "fashion" / "validation.csv").open(
                encoding="utf-8"
            ) as handle:
                validation = list(csv.DictReader(handle))
            for user_id in {row["user_id"] for row in train}:
                user_train = [
                    row["timestamp"] for row in train if row["user_id"] == user_id
                ]
                user_validation = [
                    row["timestamp"]
                    for row in validation
                    if row["user_id"] == user_id
                ]
                if user_validation:
                    self.assertLessEqual(max(user_train), min(user_validation))


if __name__ == "__main__":
    unittest.main()
