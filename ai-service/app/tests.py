import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import BehaviorEvent, KBDocument


class DatabaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.Session = sessionmaker(
            bind=cls.engine,
            autoflush=False,
            expire_on_commit=False,
        )
        Base.metadata.create_all(cls.engine)

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        with self.Session() as db:
            for table in reversed(Base.metadata.sorted_tables):
                db.execute(table.delete())
            db.commit()


class AIAPITests(DatabaseTestCase):
    def test_event_ingest_extracts_product_and_domain_from_payload(self):
        response = self.client.post(
            "/events/ingest/",
            json={
                "event_type": "view_product",
                "customer_id": 7,
                "payload": {"product_id": 12, "domain": "electronics"},
            },
        )
        self.assertEqual(response.status_code, 201)
        with self.Session() as db:
            event = db.scalar(select(BehaviorEvent))
            self.assertEqual(event.product_id, 12)
            self.assertEqual(event.domain, "electronics")
            self.assertIsNotNone(event.occurred_at)

    @patch("app.main.recommend")
    def test_recommendation_keeps_items_contract(self, recommend):
        recommend.return_value = [
            {
                "id": 3,
                "title": "Laptop",
                "recommendation_score": 0.8,
                "component_scores": {
                    "lstm": 0.7,
                    "graph": 0.9,
                    "semantic": 0.6,
                },
                "fallback_used": False,
            }
        ]
        response = self.client.post(
            "/behavior/recommend-products/",
            json={"customer_id": 7, "domain": "electronics", "limit": 4},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["id"], 3)

    @patch("app.main.llm.generate", return_value=None)
    @patch("app.main.get_vector_store")
    @patch("app.main.recommend", return_value=[])
    def test_chat_uses_extractive_fallback(
        self, recommend, vector_store, generate
    ):
        vector_store.return_value.search.return_value = [
            {
                "type": "document",
                "source": "policy:return",
                "title": "Return policy",
                "content": "Returns are accepted within seven days.",
                "score": 0.9,
            }
        ]
        response = self.client.post(
            "/chat/advice/",
            json={"customer_id": 7, "message": "How can I return an item?"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "rag_extractive")
        self.assertEqual(body["citations"], ["policy:return"])
        self.assertEqual(body["citation_details"][0]["type"], "document")

    @patch("app.main.fetch_products", return_value=[])
    @patch("app.main.get_vector_store")
    def test_kb_reindex_rebuilds_index(self, vector_store, fetch_products):
        vector_store.return_value.rebuild.return_value = {
            "indexed": 1,
            "documents": 1,
            "products": 0,
            "backend": "faiss",
        }
        response = self.client.post(
            "/kb/reindex/",
            json={
                "documents": [
                    {
                        "title": "Shipping",
                        "content": "Three days",
                        "source": "policy:shipping",
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 200)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(KBDocument)).all()), 1)
        self.assertEqual(response.json()["indexed"], 1)


class GraphWorkerTests(DatabaseTestCase):
    @patch("graph.service.upsert_event")
    def test_graph_sync_is_idempotent_after_success(self, upsert):
        from graph.service import sync_pending_events

        with self.Session() as db:
            db.add(
                BehaviorEvent(
                    event_type="view_product",
                    customer_id=1,
                    product_id=2,
                )
            )
            db.commit()
            self.assertEqual(sync_pending_events(db)["synced"], 1)
            self.assertEqual(sync_pending_events(db)["processed"], 0)
        upsert.assert_called_once()

    @patch("graph.service.upsert_event", side_effect=RuntimeError("neo4j down"))
    def test_graph_sync_records_retry_state(self, upsert):
        from graph.service import sync_pending_events

        with self.Session() as db:
            event = BehaviorEvent(
                event_type="view_product",
                customer_id=1,
                product_id=2,
            )
            db.add(event)
            db.commit()
            event_id = event.id
            self.assertEqual(sync_pending_events(db)["failed"], 1)

        with self.Session() as db:
            event = db.get(BehaviorEvent, event_id)
            self.assertEqual(event.graph_sync_attempts, 1)
            self.assertIn("neo4j down", event.graph_sync_error)


if __name__ == "__main__":
    unittest.main()
