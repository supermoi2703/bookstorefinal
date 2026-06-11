from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Category, Product


class ProductAPITests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Electronics", slug="electronics")
        self.product = Product.objects.create(
            title="Test Laptop",
            creator_or_brand="Test Brand",
            price="1000.00",
            stock=5,
            category=self.category,
            domain="electronics",
            source="amazon_electronics",
            external_id="ASIN-1",
        )

    def test_product_contract_and_external_lookup(self):
        response = self.client.get(
            "/products/",
            {"source": "amazon_electronics", "external_id": "ASIN-1"},
        )
        self.assertEqual(response.status_code, 200)
        product = response.json()[0]
        self.assertEqual(product["id"], self.product.id)
        self.assertEqual(product["title"], "Test Laptop")
        self.assertEqual(product["domain"], "electronics")
        self.assertEqual(product["effective_price"], "1000.00")

    def test_unique_source_external_id(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.create(
                    title="Duplicate",
                    source="amazon_electronics",
                    external_id="ASIN-1",
                )
