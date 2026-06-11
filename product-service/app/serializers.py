from rest_framework import serializers

from .models import Category, Product


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = "__all__"

    def get_product_count(self, obj):
        return obj.products.filter(is_active=True).count()


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source="category.name", read_only=True, default=None
    )
    effective_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    discount_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = "__all__"


class ProductListSerializer(ProductSerializer):
    class Meta(ProductSerializer.Meta):
        fields = [
            "id",
            "title",
            "author",
            "creator_or_brand",
            "description",
            "price",
            "discount_price",
            "effective_price",
            "discount_percent",
            "stock",
            "category",
            "category_name",
            "domain",
            "source",
            "external_id",
            "metadata",
            "image_url",
            "is_featured",
            "is_active",
            "created_at",
        ]
