import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from graph.service import (
    get_recommended_products,
    graph_search,
    health as graph_health,
)
from model_behavior.registry import registry_status
from rag import llm
from rag.vector_store import fetch_products, get_vector_store
from recommendation.hybrid import recommend, resolve_candidate

from .crud import (
    active_kb_documents,
    behavior_profile_scores,
    upsert_behavior_profile,
    upsert_kb_document,
)
from .database import get_db, init_db
from .models import BehaviorEvent, utcnow
from .schemas import (
    BehaviorScoreRequest,
    ChatAdviceRequest,
    EventIngestRequest,
    GraphRecommendationRequest,
    KBReindexRequest,
    KBDocumentInput,
    RecommendationRequest,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="ProductStore AI Service",
    version="2.0.0",
    description="Hybrid LSTM, Neo4j and vector RAG recommendation service.",
    lifespan=lifespan,
)


def detect_domain(message):
    text_value = message.lower()
    if any(word in text_value for word in ("sách", "book", "tiểu thuyết", "đọc")):
        return "book"
    if any(
        word in text_value
        for word in ("laptop", "điện thoại", "tai nghe", "electronics", "điện tử")
    ):
        return "electronics"
    if any(
        word in text_value for word in ("áo", "quần", "giày", "fashion", "thời trang")
    ):
        return "fashion"
    return None


def citation_details(contexts):
    return [
        {
            "source": item.get("source", "unknown"),
            "title": item.get("title", ""),
            "type": item.get("type", "document"),
            "score": item.get("score"),
        }
        for item in contexts
    ]


def extractive_answer(contexts, products):
    if contexts:
        evidence = " ".join(
            f"{item.get('title')}: {item.get('content', '')[:220]}."
            for item in contexts[:3]
        )
        return f"Dựa trên dữ liệu đã truy xuất: {evidence}"
    if products:
        names = ", ".join(
            f"{item.get('title')} (ID {item.get('id')})" for item in products[:3]
        )
        return f"Các sản phẩm phù hợp nhất hiện tại: {names}."
    return (
        "Tôi chưa tìm thấy dữ liệu phù hợp. Hãy bổ sung nhóm sản phẩm, ngân sách "
        "hoặc mục đích sử dụng để nhận gợi ý chính xác hơn."
    )


@app.get("/health/")
def health(db: Session = Depends(get_db)):
    database = {"available": True}
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        database = {"available": False, "error": str(exc)}
    components = {
        "database": database,
        "neo4j": graph_health(),
        "vector_store": get_vector_store().status(),
        "model_registry": registry_status(),
        "llm": llm.status(),
    }
    payload = {
        "status": "ok" if database["available"] else "degraded",
        "service": "ai-service",
        "framework": "FastAPI",
        "components": components,
    }
    if not database["available"]:
        raise HTTPException(status_code=503, detail=payload)
    return payload


@app.post("/events/ingest/", status_code=status.HTTP_201_CREATED)
def ingest_event(body: EventIngestRequest, db: Session = Depends(get_db)):
    event = BehaviorEvent(
        event_type=body.event_type,
        customer_id=body.customer_id,
        session_id=body.session_id,
        product_id=body.product_id,
        domain=body.domain or "",
        occurred_at=body.occurred_at or utcnow(),
        payload=body.payload,
    )
    db.add(event)
    db.commit()
    return {"status": "ingested"}


@app.post("/behavior/score/")
def behavior_score(body: BehaviorScoreRequest, db: Session = Depends(get_db)):
    scores = behavior_profile_scores(db, body.customer_id)
    upsert_behavior_profile(db, body.customer_id, scores)
    return {"customer_id": body.customer_id, "scores": scores}


@app.post("/behavior/recommend-products/")
def behavior_recommend(
    body: RecommendationRequest, db: Session = Depends(get_db)
):
    items = recommend(
        db,
        body.customer_id,
        limit=body.limit,
        domain=body.domain,
        query=body.query,
    )
    return {
        "customer_id": body.customer_id,
        "domain": body.domain,
        "items": items,
        "fallback_used": bool(items and items[0].get("fallback_used")),
    }


@app.post("/graph/recommendations/")
def graph_recommend(body: GraphRecommendationRequest):
    rows = (
        get_recommended_products(body.customer_id, body.limit, body.domain)
        if body.customer_id
        else []
    )
    if not rows:
        rows = graph_search(limit=body.limit, domain=body.domain)
    items = []
    for row in rows:
        product = resolve_candidate(row)
        if product:
            product["recommendation_score"] = row.get(
                "score", row.get("engagement_score", 0)
            )
            product["recommendation_source"] = "kb_graph"
            items.append(product)
    return {
        "customer_id": body.customer_id,
        "source": "kb_graph",
        "items": items,
    }


@app.post("/kb/reindex/")
def kb_reindex(body: KBReindexRequest, db: Session = Depends(get_db)):
    for document in body.documents:
        upsert_kb_document(db, document)
    try:
        result = get_vector_store().rebuild(
            active_kb_documents(db), fetch_products()
        )
    except Exception as exc:
        logger.exception("KB reindex failed")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "upserted": len(body.documents),
                "error": str(exc),
            },
        ) from exc
    return {"status": "ok", "upserted": len(body.documents), **result}


DEMO_DOCUMENTS = [
    KBDocumentInput(
        title="Chính sách giao hàng",
        content="Đơn hàng tiêu chuẩn giao 3-5 ngày. Giao nhanh 1-2 ngày nội thành.",
        source="policy:shipping",
        topic="shipping",
    ),
    KBDocumentInput(
        title="Chính sách đổi trả",
        content="Đổi trả trong 7 ngày cho sản phẩm lỗi hoặc sai mô tả. Cần hóa đơn.",
        source="policy:return",
        topic="return",
    ),
    KBDocumentInput(
        title="Phương thức thanh toán",
        content="Hỗ trợ COD, chuyển khoản ngân hàng và thẻ tín dụng.",
        source="faq:payment",
        topic="payment",
    ),
]


@app.post("/kb/seed-demo/")
def seed_demo_kb(db: Session = Depends(get_db)):
    for document in DEMO_DOCUMENTS:
        upsert_kb_document(db, document)
    return {"status": "ok", "upserted": len(DEMO_DOCUMENTS)}


@app.post("/chat/advice/")
def chat_advice(body: ChatAdviceRequest, db: Session = Depends(get_db)):
    domain = body.domain or detect_domain(body.message)
    contexts = get_vector_store().search(body.message, limit=5)
    products = (
        recommend(
            db,
            body.customer_id,
            limit=4,
            domain=domain,
            query=body.message,
        )
        if body.customer_id
        else []
    )
    try:
        answer = llm.generate(body.message, contexts, products)
        source = "rag_llm" if answer else "rag_extractive"
    except Exception as exc:
        logger.warning("LLM generation failed, using extractive fallback: %s", exc)
        answer = None
        source = "rag_extractive"
    answer = answer or extractive_answer(contexts, products)
    details = citation_details(contexts)
    return {
        "answer": answer,
        "citations": [item["source"] for item in details],
        "citation_details": details,
        "recommended_products": products,
        "domain": domain,
        "source": source,
    }
