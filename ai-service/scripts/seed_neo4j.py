import argparse
import csv
import json
import os
import sys
from pathlib import Path

import requests
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from graph.service import rebuild_similar_edges


ACTION_RELATIONSHIPS = {
    "VIEW": "VIEWED",
    "CLICK": "CLICKED",
    "ADD_TO_CART": "ADDED_TO_CART",
    "PURCHASE": "PURCHASED",
    "RATE": "RATED",
    "READ": "READ",
}


def read_csv(path):
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def product_mapping(product_service_url):
    response = requests.get(f"{product_service_url.rstrip('/')}/products/", timeout=60)
    response.raise_for_status()
    payload = response.json()
    products = payload.get("results", payload) if isinstance(payload, dict) else payload
    return {
        (str(product.get("source")), str(product.get("external_id"))): product
        for product in products
        if product.get("external_id")
    }


def chunks(rows, size=1000):
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def seed(processed_root, product_service_url, clear=False):
    driver = GraphDatabase.driver(
        os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        auth=(
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "productstore123"),
        ),
    )
    mapping = product_mapping(product_service_url)
    products = []
    interactions = []
    for domain_dir in Path(processed_root).iterdir():
        if not domain_dir.is_dir() or not (domain_dir / "interactions.csv").exists():
            continue
        for row in read_csv(domain_dir / "products.csv"):
            catalog = mapping.get((row["source"], row["external_id"]), {})
            products.append(
                {
                    "graph_key": f"{row['source']}:{row['external_id']}",
                    "catalog_id": catalog.get("id"),
                    "source": row["source"],
                    "external_id": row["external_id"],
                    "domain": row["domain"],
                    "title": row["title"],
                    "category": row.get("category", ""),
                }
            )
        for row in read_csv(domain_dir / "interactions.csv"):
            interactions.append(
                {
                    "user_id": f"{row['source']}:{row['user_id']}",
                    "graph_key": f"{row['source']}:{row['item_id']}",
                    "relationship": ACTION_RELATIONSHIPS[row["action"]],
                    "occurred_at": row["timestamp"],
                    "rating": float(row["rating"]) if row.get("rating") else None,
                }
            )
    with driver.session() as session:
        if clear:
            session.run("MATCH (n) DETACH DELETE n").consume()
        session.run(
            "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE"
        ).consume()
        session.run(
            "CREATE CONSTRAINT catalog_product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.graph_key IS UNIQUE"
        ).consume()
        for batch in chunks(products):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (p:Product {graph_key: row.graph_key})
                SET p.catalog_id = row.catalog_id, p.source = row.source,
                    p.external_id = row.external_id, p.domain = row.domain,
                    p.title = row.title, p.category = row.category
                MERGE (d:Domain {name: row.domain})
                MERGE (p)-[:IN_DOMAIN]->(d)
                FOREACH (_ IN CASE WHEN row.category <> '' THEN [1] ELSE [] END |
                  MERGE (c:Category {key: row.domain + ':' + row.category})
                  SET c.name = row.category
                  MERGE (p)-[:IN_CATEGORY]->(c)
                )
                """,
                rows=batch,
            ).consume()
        for relationship in sorted(set(ACTION_RELATIONSHIPS.values())):
            selected = [row for row in interactions if row["relationship"] == relationship]
            for batch in chunks(selected):
                session.run(
                    f"""
                    UNWIND $rows AS row
                    MERGE (u:User {{user_id: row.user_id}})
                    MATCH (p:Product {{graph_key: row.graph_key}})
                    CREATE (u)-[r:{relationship}]->(p)
                    SET r.occurred_at = row.occurred_at, r.rating = row.rating
                    """,
                    rows=batch,
                ).consume()
    driver.close()
    similar = rebuild_similar_edges()
    return {
        "products": len(products),
        "interactions": len(interactions),
        **similar,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--processed-root", default=str(BASE_DIR / "data" / "processed")
    )
    parser.add_argument(
        "--product-service-url",
        default=os.environ.get("PRODUCT_SERVICE_URL", "http://localhost:8002"),
    )
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            seed(args.processed_root, args.product_service_url, args.clear), indent=2
        )
    )


if __name__ == "__main__":
    main()
