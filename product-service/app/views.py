from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Category, Product
from .serializers import CategorySerializer, ProductListSerializer, ProductSerializer


class CategoryListCreate(APIView):
    def get(self, request):
        serializer = CategorySerializer(
            Category.objects.filter(is_active=True), many=True
        )
        return Response(serializer.data)

    def post(self, request):
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CategoryDetail(APIView):
    def _get(self, pk):
        try:
            return Category.objects.get(pk=pk)
        except Category.DoesNotExist:
            return None

    def get(self, request, pk):
        category = self._get(pk)
        if not category:
            return Response({"error": "Category not found"}, status=404)
        return Response(CategorySerializer(category).data)

    def put(self, request, pk):
        category = self._get(pk)
        if not category:
            return Response({"error": "Category not found"}, status=404)
        serializer = CategorySerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        category = self._get(pk)
        if not category:
            return Response({"error": "Category not found"}, status=404)
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductListCreate(APIView):
    def get(self, request):
        products = Product.objects.filter(is_active=True).select_related("category")
        q = request.query_params.get("q")
        if q:
            products = products.filter(
                Q(title__icontains=q)
                | Q(author__icontains=q)
                | Q(creator_or_brand__icontains=q)
                | Q(description__icontains=q)
            )
        if request.query_params.get("category"):
            products = products.filter(category_id=request.query_params["category"])
        if request.query_params.get("domain"):
            products = products.filter(domain=request.query_params["domain"])
        if request.query_params.get("source"):
            products = products.filter(source=request.query_params["source"])
        if request.query_params.get("external_id"):
            products = products.filter(external_id=request.query_params["external_id"])
        if request.query_params.get("min_price"):
            products = products.filter(price__gte=request.query_params["min_price"])
        if request.query_params.get("max_price"):
            products = products.filter(price__lte=request.query_params["max_price"])
        if request.query_params.get("featured") == "1":
            products = products.filter(is_featured=True)

        sort = request.query_params.get("sort", "-created_at")
        valid_sorts = {"price", "-price", "title", "-title", "created_at", "-created_at"}
        products = products.order_by(sort if sort in valid_sorts else "-created_at")
        return Response(ProductListSerializer(products, many=True).data)

    def post(self, request):
        serializer = ProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProductDetail(APIView):
    def _get(self, pk):
        try:
            return Product.objects.select_related("category").get(pk=pk)
        except Product.DoesNotExist:
            return None

    def get(self, request, pk):
        product = self._get(pk)
        if not product:
            return Response({"error": "Product not found"}, status=404)
        return Response(ProductSerializer(product).data)

    def put(self, request, pk):
        product = self._get(pk)
        if not product:
            return Response({"error": "Product not found"}, status=404)
        serializer = ProductSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        product = self._get(pk)
        if not product:
            return Response({"error": "Product not found"}, status=404)
        product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductSearch(APIView):
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response({"query": "", "results": [], "count": 0})
        products = Product.objects.filter(
            Q(title__icontains=query)
            | Q(author__icontains=query)
            | Q(creator_or_brand__icontains=query)
            | Q(description__icontains=query),
            is_active=True,
        ).select_related("category")
        data = ProductListSerializer(products, many=True).data
        return Response({"query": query, "count": len(data), "results": data})


class FeaturedProducts(APIView):
    def get(self, request):
        products = Product.objects.filter(
            is_active=True, is_featured=True
        ).select_related("category")[:12]
        return Response(ProductListSerializer(products, many=True).data)
