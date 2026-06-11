from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import BehaviorEvent, BehaviorProfile, KBDocument, utcnow
from .schemas import KBDocumentInput


def behavior_profile_scores(db: Session, customer_id: int):
    rows = db.execute(
        select(BehaviorEvent.event_type, func.count(BehaviorEvent.id))
        .where(BehaviorEvent.customer_id == customer_id)
        .group_by(BehaviorEvent.event_type)
    ).all()
    counts = Counter({event_type: total for event_type, total in rows})
    event_count = sum(counts.values())
    if event_count == 0:
        return {"engagement": 0.0, "purchase_intent": 0.0, "churn_risk": 1.0}
    views = counts["view_product"] + counts["view_product_list"]
    carts = counts["add_to_cart"]
    purchases = counts["order_created"] + counts["purchase"]
    checkouts = counts["checkout_start"]
    engagement = min(1.0, (views + carts * 2 + checkouts * 3) / max(10, event_count))
    purchase_intent = min(
        1.0, (carts * 2 + checkouts * 3 + purchases * 4) / max(12, event_count)
    )
    churn_risk = max(0.0, 1.0 - (engagement * 0.4 + purchase_intent * 0.6))
    return {
        "engagement": round(engagement, 4),
        "purchase_intent": round(purchase_intent, 4),
        "churn_risk": round(churn_risk, 4),
    }


def upsert_behavior_profile(db: Session, customer_id: int, scores: dict):
    profile = db.scalar(
        select(BehaviorProfile).where(BehaviorProfile.customer_id == customer_id)
    )
    if profile is None:
        profile = BehaviorProfile(customer_id=customer_id, scores=scores)
        db.add(profile)
    else:
        profile.scores = scores
        profile.updated_at = utcnow()
    db.commit()
    db.refresh(profile)
    return profile


def upsert_kb_document(db: Session, document: KBDocumentInput):
    row = db.scalar(
        select(KBDocument).where(
            KBDocument.title == document.title,
            KBDocument.source == document.source,
        )
    )
    values = document.model_dump()
    metadata = values.pop("metadata")
    if row is None:
        row = KBDocument(**values, metadata_json=metadata)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
        row.metadata_json = metadata
        row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def active_kb_documents(db: Session):
    return list(
        db.scalars(
            select(KBDocument)
            .where(KBDocument.is_active.is_(True))
            .order_by(KBDocument.updated_at.desc())
        )
    )
