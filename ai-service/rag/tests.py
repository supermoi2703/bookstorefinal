import unittest

import numpy as np

from rag.vector_store import VectorStore


class VectorStoreTests(unittest.TestCase):
    def test_numpy_search_filters_type_and_domain(self):
        store = VectorStore()
        store.metadata = [
            {"type": "product", "id": 1, "domain": "book", "title": "Book"},
            {
                "type": "product",
                "id": 2,
                "domain": "electronics",
                "title": "Laptop",
            },
            {"type": "document", "id": 3, "title": "Policy"},
        ]
        store.vectors = np.asarray(
            [[1.0, 0.0], [0.0, 1.0], [0.7, 0.3]], dtype=np.float32
        )
        store.index = None
        store.encode = lambda texts: np.asarray([[1.0, 0.0]], dtype=np.float32)
        result = store.search(
            "book", limit=2, record_type="product", domain="book"
        )
        self.assertEqual([item["id"] for item in result], [1])

    def test_semantic_pairs_stay_inside_domain(self):
        store = VectorStore()
        store.metadata = [
            {"type": "product", "id": 1, "domain": "book"},
            {"type": "product", "id": 2, "domain": "book"},
            {"type": "product", "id": 3, "domain": "fashion"},
        ]
        store.vectors = np.asarray(
            [[1.0, 0.0], [0.99, 0.01], [1.0, 0.0]], dtype=np.float32
        )
        store.index = None
        pairs = store.semantic_pairs(neighbors=2, threshold=0.9)
        self.assertEqual(len(pairs), 1)
        self.assertEqual((pairs[0]["left"], pairs[0]["right"]), (1, 2))
