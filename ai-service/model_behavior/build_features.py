from collections import defaultdict

from sqlalchemy import select

from app.database import session_scope
from app.models import BehaviorEvent


def build_feature_rows(db):
    grouped = defaultdict(
        lambda: {
            "view": 0,
            "search": 0,
            "cart": 0,
            "checkout": 0,
            "order": 0,
            "wishlist": 0,
        }
    )
    events = db.scalars(
        select(BehaviorEvent).where(BehaviorEvent.customer_id.is_not(None))
    )
    for event in events:
        features = grouped[event.customer_id]
        if event.event_type == "view_product":
            features["view"] += 1
        elif event.event_type == "search_products":
            features["search"] += 1
        elif event.event_type == "add_to_cart":
            features["cart"] += 1
        elif event.event_type == "checkout_start":
            features["checkout"] += 1
        elif event.event_type == "order_created":
            features["order"] += 1
        elif event.event_type == "wishlist_add":
            features["wishlist"] += 1
    return [{"customer_id": customer_id, **features} for customer_id, features in grouped.items()]


if __name__ == "__main__":
    with session_scope() as session:
        rows = build_feature_rows(session)
    print(f"Built {len(rows)} feature rows")
    for row in rows[:10]:
        print(row)
