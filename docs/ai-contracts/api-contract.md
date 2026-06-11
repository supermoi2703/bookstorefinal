# AI Service Contracts (MVP)

## Cấu trúc thư mục tổng thể

```text
bookstore_micro_05/
├── docker-compose.yml
├── README.md
├── HUONG_DAN.md
├── docs/
│   ├── ai-contracts/
│   │   └── api-contract.md
│   └── deploy/
├── data/
│   └── data_user500.csv
├── kb/
│   └── seed_kb.py
├── plots/
├── scripts/
│   ├── generate_data.py
│   ├── seed_neo4j.py
│   └── train_models.py
├── ai-service/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── main.py
│   ├── requirements.txt
│   ├── app/
│   ├── kb/
│   ├── model_behavior/
│   ├── plots/
│   └── rag/
├── api-gateway/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── manage.py
│   ├── requirements.txt
│   ├── api_gateway/
│   ├── app/
│   └── templates/
├── cart-service/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── manage.py
│   ├── requirements.txt
│   ├── app/
│   └── cart_service/
├── customer-service/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── manage.py
│   ├── requirements.txt
│   ├── app/
│   └── customer_service/
├── order-service/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── manage.py
│   ├── requirements.txt
│   ├── app/
│   └── order_service/
├── payment-service/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── manage.py
│   ├── requirements.txt
│   ├── app/
│   └── payment_service/
├── product-service/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── manage.py
│   ├── requirements.txt
│   ├── app/
│   └── product_service/
├── rating-service/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── manage.py
│   ├── requirements.txt
│   ├── app/
│   └── rating_service/
└── shipping-service/
    ├── Dockerfile
    ├── entrypoint.sh
    ├── manage.py
    ├── requirements.txt
    ├── app/
    └── shipping_service/
```

> Đây là cấu trúc thư mục ở mức tổng quan. Mỗi service có thể chứa thêm các thư mục con như `migrations/`, `tests/`, hoặc các module nghiệp vụ riêng.

`ai-service` sử dụng FastAPI, SQLAlchemy và Uvicorn. Các service còn lại vẫn
giữ Django theo cấu trúc hiện tại.

## 1) Ingest hành vi
- Endpoint: `POST /events/ingest/`
- Body:
```json
{
  "event_type": "view_product",
  "customer_id": 12,
  "session_id": "abc",
  "product_id": 123,
  "domain": "electronics",
  "occurred_at": "2026-06-09T10:00:00Z",
  "payload": { "category": 3 }
}
```
- Response: `201 {"status":"ingested"}`

## 2) Chấm điểm hành vi
- Endpoint: `POST /behavior/score/`
- Body:
```json
{ "customer_id": 12 }
```
- Response:
```json
{
  "customer_id": 12,
  "scores": {
    "engagement": 0.75,
    "purchase_intent": 0.64,
    "churn_risk": 0.31
  }
}
```

## 3) Recommendation sách
- Endpoint: `POST /behavior/recommend-products/`
- Body:
```json
{ "customer_id": 12, "domain": "book", "query": "sách kỹ năng", "limit": 4 }
```
- Response giữ trường `items` cũ và bổ sung cho mỗi sản phẩm:
  `recommendation_score`, `component_scores`, `reason`, `model_version`,
  `fallback_used`.

## 4) Reindex KB
- Endpoint: `POST /kb/reindex/`
- Body:
```json
{
  "documents": [
    {
      "title": "Chinh sach giao hang",
      "content": "Noi dung...",
      "source": "policy",
      "topic": "shipping",
      "metadata": {}
    }
  ]
}
```
- Response: `200 {"status":"ok","upserted":1}`

## 5) Chat tư vấn
- Endpoint: `POST /chat/advice/`
- Body:
```json
{ "message": "Toi muon doi tra thi sao?" }
```
- Response:
```json
{
  "answer": "....",
  "citations": ["policy:return"],
  "citation_details": [
    {"source": "policy:return", "title": "Chính sách đổi trả", "type": "document", "score": 0.91}
  ],
  "recommended_products": [],
  "source": "rag_llm"
}
```
