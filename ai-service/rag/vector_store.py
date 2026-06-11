import json
import logging
import os
from pathlib import Path

import numpy as np
import requests

logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
METADATA_PATH = ARTIFACT_DIR / "metadata.json"
VECTOR_PATH = ARTIFACT_DIR / "vectors.npy"
FAISS_PATH = ARTIFACT_DIR / "index.faiss"
MODEL_NAME = os.environ.get(
    "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
PRODUCT_SERVICE_URL = os.environ.get(
    "PRODUCT_SERVICE_URL", "http://product-service:8000"
)

_store = None


def _normalize(vectors):
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vectors / norms


class VectorStore:
    def __init__(self):
        self.metadata = []
        self.vectors = None
        self.index = None
        self.backend = None
        self.encoder = None
        self.load()

    def _get_encoder(self):
        if self.encoder is not None:
            return self.encoder
        try:
            from sentence_transformers import SentenceTransformer

            self.encoder = SentenceTransformer(MODEL_NAME)
            self.backend = "sentence-transformers"
        except Exception as exc:
            logger.warning("Sentence transformer unavailable, using hashing: %s", exc)
            from sklearn.feature_extraction.text import HashingVectorizer

            self.encoder = HashingVectorizer(
                n_features=384, alternate_sign=False, norm="l2"
            )
            self.backend = "hashing-fallback"
        return self.encoder

    def encode(self, texts):
        encoder = self._get_encoder()
        if hasattr(encoder, "encode"):
            values = encoder.encode(
                texts, show_progress_bar=False, normalize_embeddings=True
            )
            return np.asarray(values, dtype=np.float32)
        if hasattr(encoder, "transform"):
            return np.asarray(encoder.transform(texts).toarray(), dtype=np.float32)
        raise TypeError(f"Unsupported encoder type: {type(encoder).__name__}")

    def load(self):
        if not METADATA_PATH.exists() or not VECTOR_PATH.exists():
            return
        self.metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        self.vectors = np.load(VECTOR_PATH).astype(np.float32)
        try:
            import faiss

            if FAISS_PATH.exists():
                self.index = faiss.read_index(str(FAISS_PATH))
            else:
                self.index = faiss.IndexFlatIP(self.vectors.shape[1])
                self.index.add(self.vectors)
            self.backend = "faiss"
        except Exception:
            self.index = None
            self.backend = "numpy"

    def rebuild(self, documents, products):
        records = []
        texts = []
        for document in documents:
            text = f"{document.title}. {document.content}"
            records.append(
                {
                    "type": "document",
                    "id": document.id,
                    "source": document.source,
                    "topic": document.topic,
                    "title": document.title,
                    "content": document.content,
                }
            )
            texts.append(text)
        for product in products:
            text = " ".join(
                str(product.get(field) or "")
                for field in (
                    "title",
                    "creator_or_brand",
                    "author",
                    "category_name",
                    "domain",
                    "description",
                )
            )
            records.append(
                {
                    "type": "product",
                    "id": product.get("id"),
                    "source": product.get("source"),
                    "external_id": product.get("external_id"),
                    "domain": product.get("domain"),
                    "title": product.get("title"),
                    "content": product.get("description", ""),
                }
            )
            texts.append(text)
        self.metadata = records
        self.vectors = (
            _normalize(self.encode(texts))
            if texts
            else np.empty((0, 384), dtype=np.float32)
        )
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        METADATA_PATH.write_text(
            json.dumps(records, ensure_ascii=False), encoding="utf-8"
        )
        np.save(VECTOR_PATH, self.vectors)
        try:
            import faiss

            self.index = faiss.IndexFlatIP(self.vectors.shape[1])
            if len(self.vectors):
                self.index.add(self.vectors)
            faiss.write_index(self.index, str(FAISS_PATH))
            self.backend = "faiss"
        except Exception as exc:
            logger.warning("FAISS unavailable, keeping NumPy search: %s", exc)
            self.index = None
            self.backend = "numpy"
        graph_result = {}
        try:
            from graph.service import rebuild_similar_edges, upsert_semantic_similar

            graph_result.update(rebuild_similar_edges())
            graph_result.update(upsert_semantic_similar(self.semantic_pairs()))
        except Exception as exc:
            logger.warning("Vector index built but SIMILAR graph refresh failed: %s", exc)
            graph_result = {"graph_refresh_error": str(exc)}
        return {
            "indexed": len(records),
            "documents": sum(record["type"] == "document" for record in records),
            "products": sum(record["type"] == "product" for record in records),
            "backend": self.backend,
            "embedding_model": MODEL_NAME,
            "graph": graph_result,
        }

    def semantic_pairs(self, neighbors=5, threshold=0.65):
        product_indices = [
            index
            for index, record in enumerate(self.metadata)
            if record.get("type") == "product" and record.get("id")
        ]
        if not product_indices or self.vectors is None:
            return []
        pairs = {}
        for index in product_indices:
            vector = self.vectors[index : index + 1]
            fetch = min(len(self.metadata), neighbors * 4 + 1)
            if self.index is not None:
                scores, indices = self.index.search(vector, fetch)
                ranked = zip(scores[0].tolist(), indices[0].tolist())
            else:
                scores = self.vectors @ vector[0]
                indices = np.argsort(-scores)[:fetch]
                ranked = ((float(scores[item]), int(item)) for item in indices)
            source = self.metadata[index]
            accepted = 0
            for score, candidate_index in ranked:
                if candidate_index == index or score < threshold:
                    continue
                candidate = self.metadata[candidate_index]
                if (
                    candidate.get("type") != "product"
                    or candidate.get("domain") != source.get("domain")
                    or not candidate.get("id")
                ):
                    continue
                left, right = sorted((int(source["id"]), int(candidate["id"])))
                pairs[(left, right)] = max(score, pairs.get((left, right), 0.0))
                accepted += 1
                if accepted >= neighbors:
                    break
        return [
            {"left": left, "right": right, "score": round(float(score), 6)}
            for (left, right), score in pairs.items()
        ]

    def search(self, query, limit=10, record_type=None, domain=None):
        if not query or self.vectors is None or not len(self.metadata):
            return []
        vector = _normalize(self.encode([query]))
        fetch_limit = min(len(self.metadata), max(limit * 5, limit))
        if self.index is not None:
            scores, indices = self.index.search(vector, fetch_limit)
            pairs = zip(scores[0].tolist(), indices[0].tolist())
        else:
            scores = self.vectors @ vector[0]
            indices = np.argsort(-scores)[:fetch_limit]
            pairs = ((float(scores[index]), int(index)) for index in indices)
        results = []
        for score, index in pairs:
            if index < 0:
                continue
            record = self.metadata[index]
            if record_type and record.get("type") != record_type:
                continue
            if domain and record.get("domain") != domain:
                continue
            results.append({**record, "score": round(float(score), 6)})
            if len(results) >= limit:
                break
        return results

    def status(self):
        return {
            "available": self.vectors is not None and bool(self.metadata),
            "records": len(self.metadata),
            "backend": self.backend,
            "embedding_model": MODEL_NAME,
        }


def get_vector_store():
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


def fetch_products():
    response = requests.get(f"{PRODUCT_SERVICE_URL}/products/", timeout=20)
    response.raise_for_status()
    payload = response.json()
    return payload.get("results", payload) if isinstance(payload, dict) else payload
