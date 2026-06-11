import csv
import hashlib
import json
import random
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .adapters import ADAPTERS


INTERACTION_FIELDS = [
    "source",
    "domain",
    "user_id",
    "item_id",
    "action",
    "timestamp",
    "rating",
]
PRODUCT_FIELDS = [
    "source",
    "domain",
    "external_id",
    "title",
    "creator_or_brand",
    "description",
    "category",
    "price",
    "image_url",
    "stock",
    "metadata",
]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _filter_k_core(rows, minimum=5):
    filtered = rows
    while True:
        users = Counter(row.user_id for row in filtered)
        items = Counter(row.item_id for row in filtered)
        next_rows = [
            row
            for row in filtered
            if users[row.user_id] >= minimum and items[row.item_id] >= minimum
        ]
        if len(next_rows) == len(filtered):
            return next_rows
        filtered = next_rows


def _write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            data = asdict(row)
            if isinstance(data.get("metadata"), dict):
                data["metadata"] = json.dumps(
                    data["metadata"], ensure_ascii=False, sort_keys=True
                )
            writer.writerow(data)


def _temporal_split(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row.user_id, []).append(row)
    train, validation, test = [], [], []
    for user_rows in grouped.values():
        ordered = sorted(user_rows, key=lambda row: (row.timestamp, row.item_id))
        count = len(ordered)
        train_end = max(1, int(count * 0.70))
        validation_end = max(train_end + 1, int(count * 0.85))
        validation_end = min(validation_end, count - 1)
        train.extend(ordered[:train_end])
        validation.extend(ordered[train_end:validation_end])
        test.extend(ordered[validation_end:])
    key = lambda row: (row.timestamp, row.user_id, row.item_id)
    return sorted(train, key=key), sorted(validation, key=key), sorted(test, key=key)


def prepare_dataset(config, output_root):
    adapter_cls = ADAPTERS[config["adapter"]]
    adapter = adapter_cls(config["interactions"], config.get("metadata"))
    max_interactions = int(config.get("max_interactions", 100_000))
    max_products = int(config.get("max_products", 5_000))
    minimum = int(config.get("min_interactions", 5))

    raw_rows = []
    scanned_interactions = 0
    rng = random.Random(42)
    for interaction in adapter.interactions():
        if not interaction.user_id or not interaction.item_id:
            continue
        scanned_interactions += 1
        if len(raw_rows) < max_interactions:
            raw_rows.append(interaction)
            continue
        replacement = rng.randint(0, scanned_interactions - 1)
        if replacement < max_interactions:
            raw_rows[replacement] = interaction
    rows = _filter_k_core(raw_rows, minimum)
    train, validation, test = _temporal_split(rows)

    used_items = {row.item_id for row in rows}
    products = []
    for product in adapter.products() or []:
        if not product.external_id or not product.title:
            continue
        if used_items and product.external_id not in used_items:
            continue
        products.append(product)
        if len(products) >= max_products:
            break

    target = Path(output_root) / adapter.domain
    _write_csv(target / "interactions.csv", rows, INTERACTION_FIELDS)
    _write_csv(target / "train.csv", train, INTERACTION_FIELDS)
    _write_csv(target / "validation.csv", validation, INTERACTION_FIELDS)
    _write_csv(target / "test.csv", test, INTERACTION_FIELDS)
    _write_csv(target / "products.csv", products, PRODUCT_FIELDS)

    manifest = {
        "source": adapter.source,
        "domain": adapter.domain,
        "license": adapter.license_name,
        "citation_url": adapter.citation_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": {
            "interactions": str(adapter.interactions_path),
            "interactions_sha256": sha256(adapter.interactions_path),
            "metadata": str(adapter.metadata_path) if adapter.metadata_path else None,
            "metadata_sha256": sha256(adapter.metadata_path)
            if adapter.metadata_path
            else None,
        },
        "counts": {
            "raw_interactions": len(raw_rows),
            "scanned_interactions": scanned_interactions,
            "interactions": len(rows),
            "users": len({row.user_id for row in rows}),
            "items": len({row.item_id for row in rows}),
            "products": len(products),
            "train": len(train),
            "validation": len(validation),
            "test": len(test),
        },
        "action_distribution": dict(Counter(row.action for row in rows)),
        "split": {"strategy": "per_user_temporal", "train": 0.70, "validation": 0.15, "test": 0.15},
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def prepare_all(config_path, output_root):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    manifests = [
        prepare_dataset(dataset, output_root) for dataset in config["datasets"]
    ]
    root_manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "datasets": manifests,
    }
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(
        json.dumps(root_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return root_manifest
