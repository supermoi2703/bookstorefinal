import logging
import os
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select

logger = logging.getLogger(__name__)

EVENT_RELATIONSHIPS = {
    "view": "VIEWED",
    "view_product": "VIEWED",
    "view_product_list": "VIEWED",
    "click": "CLICKED",
    "click_product": "CLICKED",
    "add_to_cart": "ADDED_TO_CART",
    "order_created": "PURCHASED",
    "purchase": "PURCHASED",
    "rate": "RATED",
    "rating": "RATED",
    "read": "READ",
}

_driver = None


def get_driver():
    global _driver
    if _driver is None:
        from neo4j import GraphDatabase

        _driver = GraphDatabase.driver(
            os.environ.get("NEO4J_URI", "bolt://neo4j:7687"),
            auth=(
                os.environ.get("NEO4J_USER", "neo4j"),
                os.environ.get("NEO4J_PASSWORD", "productstore123"),
            ),
        )
    return _driver


def health():
    try:
        get_driver().verify_connectivity()
        return {"available": True}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def ensure_schema():
    queries = [
        "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
        "CREATE CONSTRAINT catalog_product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.graph_key IS UNIQUE",
        "CREATE CONSTRAINT domain_name IF NOT EXISTS FOR (d:Domain) REQUIRE d.name IS UNIQUE",
        "CREATE CONSTRAINT category_key IF NOT EXISTS FOR (c:Category) REQUIRE c.key IS UNIQUE",
    ]
    with get_driver().session() as session:
        for query in queries:
            session.run(query).consume()


def graph_key(catalog_id=None, source="", external_id=""):
    if catalog_id is not None:
        return f"catalog:{catalog_id}"
    return f"{source}:{external_id}"


def upsert_event(event):
    relationship = EVENT_RELATIONSHIPS.get(event.event_type.lower())
    if not relationship or not event.customer_id or not event.product_id:
        return False
    payload = event.payload or {}
    domain = event.domain or payload.get("domain") or "general"
    category = str(payload.get("category") or "")
    occurred_at = event.occurred_at or event.created_at
    key = graph_key(catalog_id=event.product_id)
    query = f"""
    MERGE (u:User {{user_id: $user_id}})
    MERGE (p:Product {{graph_key: $graph_key}})
    SET p.catalog_id = $product_id,
        p.domain = $domain,
        p.category = $category
    MERGE (d:Domain {{name: $domain}})
    MERGE (p)-[:IN_DOMAIN]->(d)
    FOREACH (_ IN CASE WHEN $category <> '' THEN [1] ELSE [] END |
      MERGE (c:Category {{key: $domain + ':' + $category}})
      SET c.name = $category
      MERGE (p)-[:IN_CATEGORY]->(c)
    )
    WITH u, p
    MERGE (u)-[r:{relationship} {{event_id: $event_id}}]->(p)
    SET r.occurred_at = $occurred_at,
        r.session_id = $session_id
    """
    with get_driver().session() as session:
        session.run(
            query,
            user_id=str(event.customer_id),
            graph_key=key,
            product_id=event.product_id,
            domain=domain,
            category=category,
            event_id=event.id,
            occurred_at=occurred_at.isoformat(),
            session_id=event.session_id,
        ).consume()
    return True


def sync_pending_events(db, batch_size=200):
    from app.models import BehaviorEvent

    events = list(
        db.scalars(
            select(BehaviorEvent)
            .where(
                BehaviorEvent.graph_synced_at.is_(None),
                BehaviorEvent.graph_sync_attempts < 10,
            )
            .order_by(BehaviorEvent.id)
            .limit(batch_size)
        )
    )
    result = defaultdict(int)
    for event in events:
        try:
            upsert_event(event)
            event.graph_synced_at = datetime.now(timezone.utc)
            event.graph_sync_error = ""
            result["synced"] += 1
        except Exception as exc:
            event.graph_sync_attempts += 1
            event.graph_sync_error = str(exc)[:2000]
            result["failed"] += 1
            logger.warning("Graph sync failed for event %s: %s", event.id, exc)
        db.add(event)
        db.commit()
    result["processed"] = len(events)
    return dict(result)


def get_user_behavior_summary(user_id):
    try:
        with get_driver().session() as session:
            rows = session.run(
                """
                MATCH (u:User {user_id: $uid})-[r]->(p:Product)
                WHERE type(r) IN ['VIEWED','CLICKED','ADDED_TO_CART','PURCHASED','RATED','READ']
                RETURN type(r) AS action, collect(DISTINCT coalesce(p.catalog_id, p.external_id)) AS products,
                       count(r) AS total
                ORDER BY total DESC
                """,
                uid=str(user_id),
            )
            return {
                row["action"].lower(): {
                    "products": row["products"],
                    "count": row["total"],
                }
                for row in rows
            }
    except Exception as exc:
        logger.warning("User graph summary failed: %s", exc)
        return {}


def get_recommended_products(user_id, limit=50, domain=None):
    try:
        with get_driver().session() as session:
            rows = session.run(
                """
                MATCH (u:User {user_id: $uid})-[]->(seen:Product)<-[]-(peer:User)
                WHERE peer <> u
                WITH u, peer, count(DISTINCT seen) AS shared
                ORDER BY shared DESC
                LIMIT 30
                MATCH (peer)-[r]->(candidate:Product)
                WHERE NOT EXISTS { MATCH (u)-[]->(candidate) }
                  AND ($domain IS NULL OR candidate.domain = $domain)
                OPTIONAL MATCH (candidate)-[s:SIMILAR]-()
                WITH candidate, count(r) + coalesce(sum(s.score), 0.0) AS score,
                     collect(DISTINCT type(r)) AS reasons
                ORDER BY score DESC
                LIMIT $limit
                RETURN candidate.catalog_id AS product_id,
                       candidate.external_id AS external_id,
                       candidate.source AS source,
                       candidate.domain AS domain,
                       score, reasons
                """,
                uid=str(user_id),
                domain=domain,
                limit=limit,
            )
            return [dict(row) for row in rows]
    except Exception as exc:
        logger.warning("Graph recommendation failed: %s", exc)
        return []


def graph_search(query="", limit=50, domain=None):
    del query
    try:
        with get_driver().session() as session:
            rows = session.run(
                """
                MATCH (u:User)-[r]->(p:Product)
                WHERE type(r) IN ['VIEWED','CLICKED','ADDED_TO_CART','PURCHASED','RATED','READ']
                  AND ($domain IS NULL OR p.domain = $domain)
                WITH p,
                     sum(CASE type(r)
                         WHEN 'VIEWED' THEN 1
                         WHEN 'CLICKED' THEN 2
                         WHEN 'ADDED_TO_CART' THEN 3
                         WHEN 'RATED' THEN 3
                         WHEN 'READ' THEN 4
                         WHEN 'PURCHASED' THEN 5
                         ELSE 0 END) AS engagement,
                     count(DISTINCT u) AS unique_users
                ORDER BY engagement DESC
                LIMIT $limit
                RETURN p.catalog_id AS product_id, p.external_id AS external_id,
                       p.source AS source, p.domain AS domain,
                       engagement AS engagement_score, unique_users
                """,
                domain=domain,
                limit=limit,
            )
            return [dict(row) for row in rows]
    except Exception as exc:
        logger.warning("Graph popularity query failed: %s", exc)
        return []


def rebuild_similar_edges(limit_per_product=20):
    with get_driver().session() as session:
        session.run("MATCH ()-[r:SIMILAR]->() DELETE r").consume()
        category_result = session.run(
            """
            MATCH (a:Product)-[:IN_CATEGORY]->(c:Category)<-[:IN_CATEGORY]-(b:Product)
            WHERE a.graph_key < b.graph_key
            WITH a, b LIMIT 100000
            MERGE (a)-[r:SIMILAR]->(b)
            SET r.category_score = 0.6,
                r.score = coalesce(r.semantic_score, 0.0)
                          + coalesce(r.behavior_score, 0.0) + 0.6,
                r.reasons = ['category']
            RETURN count(r) AS created
            """
        ).single()
        behavior_result = session.run(
            """
            MATCH (a:Product)<-[]-(u:User)-[]->(b:Product)
            WHERE a.graph_key < b.graph_key AND a.domain = b.domain
            WITH a, b, count(DISTINCT u) AS shared_users
            WHERE shared_users >= 2
            ORDER BY shared_users DESC
            LIMIT 100000
            MERGE (a)-[r:SIMILAR]->(b)
            SET r.behavior_score = CASE
                    WHEN shared_users >= 10 THEN 1.0
                    ELSE toFloat(shared_users) / 10.0 END,
                r.score = coalesce(r.semantic_score, 0.0)
                          + coalesce(r.category_score, 0.0)
                          + CASE WHEN shared_users >= 10 THEN 1.0
                                 ELSE toFloat(shared_users) / 10.0 END,
                r.reasons = coalesce(r.reasons, []) + ['co-occurrence']
            RETURN count(r) AS created
            """
        ).single()
    return {
        "category_edges": category_result["created"] if category_result else 0,
        "behavior_edges": behavior_result["created"] if behavior_result else 0,
        "limit": limit_per_product,
    }


def upsert_semantic_similar(pairs):
    if not pairs:
        return {"semantic_edges": 0}
    with get_driver().session() as session:
        result = session.run(
            """
            UNWIND $pairs AS pair
            MATCH (a:Product {catalog_id: pair.left})
            MATCH (b:Product {catalog_id: pair.right})
            WHERE a.graph_key < b.graph_key
            MERGE (a)-[r:SIMILAR]->(b)
            SET r.semantic_score = pair.score,
                r.score = coalesce(r.category_score, 0.0)
                          + coalesce(r.behavior_score, 0.0) + pair.score,
                r.reasons = coalesce(r.reasons, []) + ['metadata-embedding']
            RETURN count(r) AS created
            """,
            pairs=pairs,
        ).single()
    return {"semantic_edges": result["created"] if result else 0}
