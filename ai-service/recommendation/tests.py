import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import BehaviorEvent
from recommendation.hybrid import recommend


class HybridRecommendationTests(unittest.TestCase):
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

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        with self.Session() as db:
            for table in reversed(Base.metadata.sorted_tables):
                db.execute(table.delete())
            db.commit()

    @patch("recommendation.hybrid._product_detail")
    @patch("recommendation.hybrid._resolve_external")
    @patch("recommendation.hybrid.get_vector_store")
    @patch("recommendation.hybrid.get_recommended_products")
    @patch("recommendation.hybrid.model_recommend")
    def test_candidate_scores_merge_on_catalog_product(
        self,
        model_recommend,
        graph_recommend,
        vector_store,
        resolve_external,
        product_detail,
    ):
        with self.Session() as db:
            db.add(
                BehaviorEvent(
                    event_type="view_product",
                    customer_id=7,
                    product_id=10,
                    domain="book",
                )
            )
            db.commit()
            product = {
                "id": 10,
                "title": "Clean Code",
                "domain": "book",
                "source": "goodreads",
                "external_id": "b10",
            }
            product_detail.return_value = product
            resolve_external.return_value = product
            model_recommend.return_value = [
                {
                    "source": "goodreads",
                    "external_id": "b10",
                    "score": 0.9,
                    "model_version": "v1",
                }
            ]
            graph_recommend.return_value = [
                {"product_id": 10, "score": 4.0, "source": "goodreads"}
            ]
            vector_store.return_value.search.return_value = [
                {"id": 10, "type": "product", "domain": "book", "score": 0.8}
            ]
            result = recommend(
                db,
                7,
                domain="book",
                limit=4,
                query="clean code",
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], 10)
        self.assertEqual(result[0]["model_version"], "v1")
        self.assertGreater(result[0]["recommendation_score"], 0.9)
        self.assertEqual(
            set(result[0]["component_scores"]),
            {"lstm", "graph", "semantic"},
        )


if __name__ == "__main__":
    unittest.main()
