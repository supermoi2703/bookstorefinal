# AI Service: three-dataset hybrid pipeline

The HTTP service is implemented with **FastAPI**, SQLAlchemy, and Uvicorn.
Interactive OpenAPI documentation is available at
`http://localhost:8008/docs` after the service starts.

The service implements the Chapter 3 pipeline with three independent academic
datasets:

| Domain | Dataset | Adapter | Normalized source |
|---|---|---|---|
| Books | UCSD Goodreads Book Graph | `GoodreadsAdapter` | `goodreads` |
| Electronics | Amazon Reviews 2023 Electronics | `AmazonElectronicsAdapter` | `amazon_electronics` |
| Fashion | H&M Personalized Fashion Recommendations | `HMFashionAdapter` | `hm` |

Raw files are intentionally excluded from Git. Review each dataset's terms and
keep its citation with the submitted report.

## 1. Prepare raw data

Place the downloaded files under:

```text
ai-service/data/raw/
  goodreads/interactions.json.gz
  goodreads/books.json.gz
  amazon/Electronics.jsonl.gz
  amazon/meta_Electronics.jsonl.gz
  hm/transactions_train.csv
  hm/articles.csv
```

Copy `ai-service/data/datasets.example.json` to
`ai-service/data/datasets.json` and adjust filenames when necessary.

Normalize, deterministically reservoir-sample each source to 100,000
interactions, filter to a 5-core subset,
and create per-user temporal train/validation/test files:

```powershell
docker compose run --rm ai-service python scripts/prepare_datasets.py
```

Outputs are written to `ai-service/data/processed/<domain>/`. Every domain has
`interactions.csv`, `train.csv`, `validation.csv`, `test.csv`, `products.csv`,
and `manifest.json` with hashes and dataset statistics.

## 2. Import the catalog

The repository previously had no committed product migration and its model did
not match the API fields. Back up an existing catalog before this upgrade. For
the academic/demo environment, recreate `product_db_data` before applying the
new initial migration if the old volume was created from that incompatible
schema.

Start databases and the product service, then import each normalized catalog:

```powershell
docker compose up -d product-db product-service
docker compose exec product-service python manage.py import_ai_catalog /data/ai-processed/book/products.csv --limit 5000
docker compose exec product-service python manage.py import_ai_catalog /data/ai-processed/electronics/products.csv --limit 5000
docker compose exec product-service python manage.py import_ai_catalog /data/ai-processed/fashion/products.csv --limit 5000
```

The importer is idempotent on `(source, external_id)`.

## 3. Train and register models

Train SimpleRNN, LSTM, and BiLSTM per domain. The best model is selected by
validation `NDCG@10`; reports also include Recall, MRR, next-action accuracy,
macro-F1, and the popularity baseline.

```powershell
docker compose run --rm ai-service python scripts/train_next_item.py --epochs 5
```

Artifacts and `registry.json` are stored in the `ai_model_artifacts` volume.
The registry records whether the model beats the popularity baseline in at
least two of the three domains.

Optional hybrid-weight optimization accepts validation cases in JSON:

```powershell
docker compose run --rm ai-service python scripts/optimize_hybrid_weights.py --input /app/data/processed/hybrid-validation.json
```

## 4. Seed graph and vector index

```powershell
docker compose up -d neo4j ai-db ai-service ai-graph-worker
docker compose exec ai-service python scripts/seed_neo4j.py --clear
```

The graph contains `User`, `Product`, `Category`, and `Domain` nodes with
behavior relationships and category-based `SIMILAR` edges. New API events are
stored in PostgreSQL first and asynchronously synchronized by
`ai-graph-worker`.

Build the vector index after the product service is available:

```powershell
curl.exe -X POST http://localhost:8008/kb/reindex/ `
  -H "Content-Type: application/json" `
  -d "{\"documents\":[]}"
```

FAISS and multilingual sentence-transformer artifacts are persisted in
`ai_rag_artifacts`.

## 5. Optional LLM

Set these environment variables before `docker compose up`:

```text
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=...
LLM_MODEL=gpt-4o-mini
```

Without an API key, or when the provider fails, chat uses an extractive
response from retrieved evidence and still returns citations and products.

## Runtime behavior

- Recommendation candidates: next-item model, Neo4j, FAISS, then popularity.
- Default weights: LSTM `0.45`, Graph `0.35`, Semantic `0.20`.
- Cold-start users use semantic, graph popularity, and catalog fallback.
- `/health/` reports PostgreSQL, Neo4j, vector index, model registry, and LLM
  configuration independently.
- FastAPI preserves the existing gateway endpoint paths and JSON contracts.

## Latest training run

Training completed on June 9, 2026 with seed `42`, five epochs, and three
candidate architectures per domain. `BiLSTM` was selected for all domains.

| Domain | Interactions | Users | Items | Test NDCG@10 | Validation baseline NDCG@10 |
|---|---:|---:|---:|---:|---:|
| Book | 49,914 | 830 | 4,619 | 0.029168 | 0.005926 |
| Electronics | 19,448 | 3,013 | 1,058 | 0.192488 | 0.123620 |
| Fashion | 56,743 | 4,673 | 3,221 | 0.147174 | 0.005435 |

Registry version: `20260609054622`. The acceptance rule passed in all three
domains. Reports and model files are stored under
`ai-service/model_behavior/artifacts/` and in the Docker model volume.

The Goodreads source uses the UCSD spoiler-review subset because the original
UCSD Poetry Google Drive links were unavailable. H&M uses a low-memory parquet
representation of the competition data. Source checksums and citations are
recorded in `ai-service/data/processed/*/manifest.json`.
