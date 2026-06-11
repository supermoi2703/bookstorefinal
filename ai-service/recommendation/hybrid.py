import logging
import os
from collections import defaultdict
from datetime import datetime

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BehaviorEvent
from graph.service import get_recommended_products, graph_search
from model_behavior.registry import recommend as model_recommend
from rag.vector_store import get_vector_store
from recommendation.weights import load_weights

logger = logging.getLogger(__name__)
PRODUCT_SERVICE_URL = os.environ.get(
    "PRODUCT_SERVICE_URL", "http://product-service:8000"
)
EVENT_ACTIONS = {
    "view_product": "VIEW",
    "view_product_list": "VIEW",
    "click_product": "CLICK",
    "add_to_cart": "ADD_TO_CART",
    "order_created": "PURCHASE",
    "rating": "RATE",
}


def _product_list(params=None):
    try:
        response = requests.get(
            f"{PRODUCT_SERVICE_URL}/products/", params=params or {}, timeout=8
        )
        if response.status_code == 200:
            payload = response.json()
            return payload.get("results", payload) if isinstance(payload, dict) else payload
    except requests.RequestException as exc:
        logger.warning("Product list failed: %s", exc)
    return []


def _product_detail(product_id):
    try:
        response = requests.get(
            f"{PRODUCT_SERVICE_URL}/products/{product_id}/", timeout=4
        )
        return response.json() if response.status_code == 200 else None
    except requests.RequestException:
        return None


def _resolve_external(source, external_id):
    products = _product_list({"source": source, "external_id": external_id})
    return products[0] if products else None


def resolve_candidate(candidate):
    if candidate.get("product_id"):
        return _product_detail(candidate["product_id"])
    if candidate.get("source") and candidate.get("external_id"):
        return _resolve_external(candidate["source"], candidate["external_id"])
    return None


def _normalize(candidates, score_field="score"):
    values = [float(candidate.get(score_field) or 0) for candidate in candidates]
    if not values:
        return candidates
    low, high = min(values), max(values)
    for candidate in candidates:
        value = float(candidate.get(score_field) or 0)
        candidate["normalized_score"] = (
            (value - low) / (high - low) if high > low else (1.0 if value else 0.0)
        )
    return candidates


def _history(db: Session, customer_id, domain=None, limit=30):
    query = (
        select(BehaviorEvent)
        .where(
            BehaviorEvent.customer_id == customer_id,
            BehaviorEvent.product_id.is_not(None),
        )
        .order_by(BehaviorEvent.occurred_at.desc(), BehaviorEvent.created_at.desc())
        .limit(limit)
    )
    if domain:
        query = query.where(BehaviorEvent.domain == domain)
    return list(reversed(list(db.scalars(query))))


def _infer_domain(db: Session, customer_id):
    event = db.scalar(
        select(BehaviorEvent)
        .where(
            BehaviorEvent.customer_id == customer_id,
            BehaviorEvent.domain != "",
        )
        .order_by(BehaviorEvent.occurred_at.desc(), BehaviorEvent.created_at.desc())
        .limit(1)
    )
    return event.domain if event else None


def _lstm_candidates(db: Session, customer_id, domain):
    events = _history(db, customer_id, domain)
    external_ids = []
    actions = []
    times = []
    previous = None
    for event in events:
        product = _product_detail(event.product_id)
        if not product or not product.get("external_id"):
            continue
        external_ids.append(product["external_id"])
        actions.append(EVENT_ACTIONS.get(event.event_type, event.event_type.upper()))
        timestamp = event.occurred_at or event.created_at
        if previous is None:
            times.append(0.0)
        else:
            hours = max(0.0, (timestamp - previous).total_seconds() / 3600)
            times.append(min(hours / 168, 1.0))
        previous = timestamp
    return model_recommend(domain, external_ids, actions, times, limit=50)


def _semantic_query(db: Session, customer_id, domain, explicit_query):
    if explicit_query:
        return explicit_query
    events = _history(db, customer_id, domain, limit=10)
    categories = [
        str((event.payload or {}).get("category"))
        for event in events
        if (event.payload or {}).get("category")
    ]
    return " ".join(categories) or f"{domain or 'general'} products"


def recommend(db: Session, customer_id, limit=4, domain=None, query=""):
    domain = domain or _infer_domain(db, customer_id)
    weights = load_weights(domain)
    candidates = defaultdict(
        lambda: {
            "lstm_score": 0.0,
            "graph_score": 0.0,
            "semantic_score": 0.0,
            "reasons": [],
            "model_version": None,
            "product": None,
        }
    )

    lstm = _normalize(_lstm_candidates(db, customer_id, domain)) if domain else []
    for item in lstm:
        product = _resolve_external(item["source"], item["external_id"])
        key = (
            f"catalog:{product['id']}"
            if product
            else (item["source"], item["external_id"])
        )
        candidates[key]["product"] = product
        candidates[key]["lstm_score"] = item["normalized_score"]
        candidates[key]["model_version"] = item["model_version"]
        candidates[key]["reasons"].append("next-item sequence")

    graph = _normalize(
        [
            {**item, "score": item.get("score", item.get("engagement_score", 0))}
            for item in get_recommended_products(customer_id, 50, domain)
        ]
    )
    for item in graph:
        key = (
            f"catalog:{item['product_id']}"
            if item.get("product_id")
            else (item.get("source"), item.get("external_id"))
        )
        if not item.get("product_id") and item.get("source") and item.get("external_id"):
            product = _resolve_external(item["source"], item["external_id"])
            if product:
                key = f"catalog:{product['id']}"
                candidates[key]["product"] = product
        candidates[key]["graph_score"] = item["normalized_score"]
        candidates[key]["reasons"].append("similar users and graph relations")

    semantic = get_vector_store().search(
        _semantic_query(db, customer_id, domain, query),
        limit=50,
        record_type="product",
        domain=domain,
    )
    semantic = _normalize(semantic)
    for item in semantic:
        key = f"catalog:{item['id']}"
        candidates[key]["semantic_score"] = item["normalized_score"]
        candidates[key]["reasons"].append("semantic similarity")

    fallback_used = False
    if not candidates:
        fallback_used = True
        popular = graph_search(limit=limit, domain=domain)
        for item in popular:
            key = (
                f"catalog:{item['product_id']}"
                if item.get("product_id")
                else (item.get("source"), item.get("external_id"))
            )
            candidates[key]["graph_score"] = 1.0
            candidates[key]["reasons"].append("popular in domain")
    if not candidates:
        fallback_used = True
        for product in _product_list({"domain": domain} if domain else {})[:limit]:
            key = f"catalog:{product['id']}"
            candidates[key]["semantic_score"] = 0.1
            candidates[key]["product"] = product
            candidates[key]["reasons"].append("catalog fallback")

    ranked = []
    for key, component in candidates.items():
        product = component["product"]
        if not product:
            if isinstance(key, str) and key.startswith("catalog:"):
                product = _product_detail(int(key.split(":", 1)[1]))
            else:
                product = _resolve_external(key[0], key[1])
        if not product or (domain and product.get("domain") != domain):
            continue
        total = sum(
            weights[name] * component[f"{name}_score"]
            for name in weights
        )
        enriched = {
            **product,
            "recommendation_score": round(total, 6),
            "component_scores": {
                name: round(component[f"{name}_score"], 6)
                for name in weights
            },
            "reason": "; ".join(dict.fromkeys(component["reasons"])),
            "model_version": component["model_version"],
            "fallback_used": fallback_used,
        }
        ranked.append(enriched)
    ranked.sort(key=lambda item: item["recommendation_score"], reverse=True)
    return ranked[:limit]
