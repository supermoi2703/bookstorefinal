from decimal import Decimal

from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    icon = models.CharField(max_length=16, blank=True, default="")
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    class Domain(models.TextChoices):
        BOOK = "book", "Book"
        ELECTRONICS = "electronics", "Electronics"
        FASHION = "fashion", "Fashion"
        GENERAL = "general", "General"

    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True, default="")
    creator_or_brand = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    stock = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    domain = models.CharField(
        max_length=32, choices=Domain.choices, default=Domain.BOOK, db_index=True
    )
    source = models.CharField(max_length=64, default="local", db_index=True)
    external_id = models.CharField(max_length=128, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    image_url = models.URLField(max_length=1000, blank=True, default="")
    publisher = models.CharField(max_length=255, blank=True, default="")
    published_year = models.PositiveIntegerField(null=True, blank=True)
    pages = models.PositiveIntegerField(null=True, blank=True)
    language = models.CharField(max_length=64, blank=True, default="")
    isbn = models.CharField(max_length=32, blank=True, default="")
    is_featured = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                name="unique_product_source_external_id",
            )
        ]
        indexes = [
            models.Index(fields=["domain", "is_active"]),
            models.Index(fields=["source", "external_id"]),
        ]

    @property
    def effective_price(self):
        return self.discount_price if self.discount_price is not None else self.price

    @property
    def discount_percent(self):
        if not self.discount_price or not self.price:
            return 0
        value = (Decimal("1") - self.discount_price / self.price) * Decimal("100")
        return max(0, int(value))

    def __str__(self):
        return self.title
