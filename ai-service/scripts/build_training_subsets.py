import argparse
import gzip
import hashlib
import io
import json
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from data_pipeline.pipeline import (  # noqa: E402
    INTERACTION_FIELDS,
    PRODUCT_FIELDS,
    _filter_k_core,
    _temporal_split,
    _write_csv,
)
from data_pipeline.schema import (  # noqa: E402
    Interaction,
    ProductRecord,
    normalize_timestamp,
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_lines(handle):
    for line in handle:
        line = line.strip()
        if line:
            yield json.loads(line)


def goodreads_rows(path):
    with zipfile.ZipFile(path) as archive:
        member = next(
            name
            for name in archive.namelist()
            if name.endswith("goodreads_reviews_spoiler_raw.json")
        )
        with archive.open(member) as binary:
            with io.TextIOWrapper(binary, encoding="utf-8") as text:
                yield from json_lines(text)


def amazon_rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        yield from json_lines(handle)


def hm_rows(path):
    import pyarrow.parquet as parquet

    source = parquet.ParquetFile(path)
    columns = ["t_dat", "customer_id", "article_id"]
    for batch in source.iter_batches(batch_size=100_000, columns=columns):
        dates = batch.column(0).to_pylist()
        users = batch.column(1).to_pylist()
        items = batch.column(2).to_pylist()
        for date, user_id, item_id in zip(dates, users, items):
            yield {
                "t_dat": date,
                "customer_id": user_id,
                "article_id": item_id,
            }


def parse_goodreads(row):
    rating = float(row.get("rating") or 0)
    return Interaction(
        source="goodreads",
        domain="book",
        user_id=str(row.get("user_id") or ""),
        item_id=str(row.get("book_id") or ""),
        action="READ" if row.get("is_read", True) else "RATE",
        timestamp=normalize_timestamp(
            row.get("date_updated")
            or row.get("read_at")
            or row.get("date_added")
        ),
        rating=rating,
    )


def parse_amazon(row):
    return Interaction(
        source="amazon_electronics",
        domain="electronics",
        user_id=str(row.get("reviewerID") or row.get("user_id") or ""),
        item_id=str(row.get("asin") or row.get("parent_asin") or ""),
        action="RATE",
        timestamp=normalize_timestamp(
            row.get("unixReviewTime")
            or row.get("timestamp")
            or row.get("sort_timestamp")
        ),
        rating=float(row.get("overall", row.get("rating", 0)) or 0),
    )


def hm_item_id(value):
    return str(value or "").zfill(10)


def parse_hm(row):
    return Interaction(
        source="hm",
        domain="fashion",
        user_id=str(row.get("customer_id") or ""),
        item_id=hm_item_id(row.get("article_id")),
        action="PURCHASE",
        timestamp=normalize_timestamp(row.get("t_dat")),
        rating=None,
    )


def select_dense_rows(
    row_factory,
    parser,
    scan_limit,
    max_interactions=60_000,
    max_items=5_000,
    min_interactions=5,
):
    user_counts = Counter()
    item_counts = Counter()
    scanned = 0
    for raw in row_factory():
        interaction = parser(raw)
        if not interaction.user_id or not interaction.item_id:
            continue
        user_counts[interaction.user_id] += 1
        item_counts[interaction.item_id] += 1
        scanned += 1
        if scanned >= scan_limit:
            break

    selected_users = {
        key for key, _ in user_counts.most_common(min(20_000, len(user_counts)))
    }
    selected_items = {
        key for key, _ in item_counts.most_common(min(max_items, len(item_counts)))
    }

    eligible = []
    rescanned = 0
    collection_limit = max_interactions * 2
    for raw in row_factory():
        interaction = parser(raw)
        rescanned += 1
        if (
            interaction.user_id in selected_users
            and interaction.item_id in selected_items
        ):
            eligible.append(interaction)
            if len(eligible) >= collection_limit:
                break
        if rescanned >= scan_limit:
            break

    dense = _filter_k_core(eligible, min_interactions)
    if len(dense) > max_interactions:
        grouped = defaultdict(list)
        for row in dense:
            grouped[row.user_id].append(row)
        selected = []
        ordered_users = sorted(
            grouped,
            key=lambda user_id: (-len(grouped[user_id]), user_id),
        )
        for user_id in ordered_users:
            user_rows = sorted(
                grouped[user_id],
                key=lambda row: (row.timestamp, row.item_id),
            )
            if len(selected) + len(user_rows) > max_interactions:
                continue
            selected.extend(user_rows)
            if len(selected) >= max_interactions:
                break
        dense = _filter_k_core(selected, min_interactions)

    if len(dense) < 1_000:
        raise RuntimeError(
            f"Dense subset is too small: {len(dense)} interactions "
            f"from {scanned} scanned rows"
        )
    dense.sort(key=lambda row: (row.timestamp, row.user_id, row.item_id))
    return dense, {
        "scanned_interactions": scanned,
        "eligible_interactions": len(eligible),
    }


def placeholder_products(rows, source, domain, label):
    item_counts = Counter(row.item_id for row in rows)
    return [
        ProductRecord(
            source=source,
            domain=domain,
            external_id=item_id,
            title=f"{label} {item_id}",
            category=label,
            metadata={"interaction_count": count},
        )
        for item_id, count in item_counts.most_common(5_000)
    ]


def hm_products(path, used_items):
    import pyarrow.parquet as parquet

    table = parquet.read_table(path)
    columns = table.column_names
    values = {name: table[name].to_pylist() for name in columns}
    products = []
    for index, raw_item_id in enumerate(values["article_id"]):
        item_id = hm_item_id(raw_item_id)
        if item_id not in used_items:
            continue

        def value(name, default=""):
            if name not in values:
                return default
            return values[name][index] or default

        products.append(
            ProductRecord(
                source="hm",
                domain="fashion",
                external_id=item_id,
                title=str(value("prod_name", value("product_type_name", item_id))),
                creator_or_brand="H&M",
                description=str(value("detail_desc")),
                category=str(
                    value("section_name", value("garment_group_name", "Fashion"))
                ),
                metadata={
                    "colour_group": value("colour_group_name"),
                    "department": value("department_name"),
                    "index_group": value("index_group_name"),
                },
            )
        )
        if len(products) >= 5_000:
            break
    return products


def write_dataset(
    output_root,
    rows,
    products,
    source_path,
    source,
    domain,
    license_name,
    citation_url,
    scan_stats,
):
    target = Path(output_root) / domain
    train, validation, test = _temporal_split(rows)
    _write_csv(target / "interactions.csv", rows, INTERACTION_FIELDS)
    _write_csv(target / "train.csv", train, INTERACTION_FIELDS)
    _write_csv(target / "validation.csv", validation, INTERACTION_FIELDS)
    _write_csv(target / "test.csv", test, INTERACTION_FIELDS)
    _write_csv(target / "products.csv", products, PRODUCT_FIELDS)
    manifest = {
        "source": source,
        "domain": domain,
        "license": license_name,
        "citation_url": citation_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": {
            "interactions": str(source_path),
            "interactions_sha256": sha256(source_path),
        },
        "counts": {
            **scan_stats,
            "interactions": len(rows),
            "users": len({row.user_id for row in rows}),
            "items": len({row.item_id for row in rows}),
            "products": len(products),
            "train": len(train),
            "validation": len(validation),
            "test": len(test),
        },
        "action_distribution": dict(Counter(row.action for row in rows)),
        "split": {
            "strategy": "per_user_temporal",
            "train": 0.70,
            "validation": 0.15,
            "test": 0.15,
        },
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw-root",
        default=str(BASE_DIR / "data" / "raw"),
    )
    parser.add_argument(
        "--output-root",
        default=str(BASE_DIR / "data" / "processed"),
    )
    args = parser.parse_args()
    raw_root = Path(args.raw_root)

    specs = [
        {
            "source": "goodreads",
            "domain": "book",
            "path": raw_root
            / "goodreads"
            / "goodreads_reviews_spoiler_raw.json.zip",
            "factory": lambda: goodreads_rows(
                raw_root
                / "goodreads"
                / "goodreads_reviews_spoiler_raw.json.zip"
            ),
            "parser": parse_goodreads,
            "scan_limit": 80_000,
            "license": "Academic use only",
            "citation": "https://mengtingwan.github.io/data/goodreads.html",
            "label": "Goodreads Book",
        },
        {
            "source": "amazon_electronics",
            "domain": "electronics",
            "path": raw_root / "amazon" / "Electronics_5.json.gz",
            "factory": lambda: amazon_rows(
                raw_root / "amazon" / "Electronics_5.json.gz"
            ),
            "parser": parse_amazon,
            "scan_limit": 300_000,
            "license": "Amazon Reviews dataset terms",
            "citation": "https://cseweb.ucsd.edu/~jmcauley/datasets/amazon_v2/",
            "label": "Amazon Electronics",
        },
        {
            "source": "hm",
            "domain": "fashion",
            "path": raw_root / "hm" / "transactions_train.parquet",
            "factory": lambda: hm_rows(
                raw_root / "hm" / "transactions_train.parquet"
            ),
            "parser": parse_hm,
            "scan_limit": 500_000,
            "license": "H&M competition data terms",
            "citation": "https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations",
            "label": "H&M Fashion",
        },
    ]

    manifests = []
    for spec in specs:
        print(f"Building {spec['domain']} subset...", flush=True)
        rows, scan_stats = select_dense_rows(
            spec["factory"],
            spec["parser"],
            spec["scan_limit"],
        )
        if spec["domain"] == "fashion":
            products = hm_products(
                raw_root / "hm" / "articles.parquet",
                {row.item_id for row in rows},
            )
        else:
            products = placeholder_products(
                rows,
                spec["source"],
                spec["domain"],
                spec["label"],
            )
        manifest = write_dataset(
            args.output_root,
            rows,
            products,
            spec["path"],
            spec["source"],
            spec["domain"],
            spec["license"],
            spec["citation"],
            scan_stats,
        )
        manifests.append(manifest)
        print(json.dumps(manifest["counts"], indent=2), flush=True)

    root_manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "datasets": manifests,
    }
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "manifest.json").write_text(
        json.dumps(root_manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(root_manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
