from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Cart, CartItem
from .serializers import CartSerializer, CartItemSerializer
import requests
import os

PRODUCT_SERVICE_URL = os.environ.get('PRODUCT_SERVICE_URL', 'http://product-service:8000')


class CartCreate(APIView):
    def post(self, request):
        customer_id = request.data.get('customer_id')
        if not customer_id:
            return Response({"error": "customer_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        cart, created = Cart.objects.get_or_create(customer_id=customer_id)
        serializer = CartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class AddCartItem(APIView):
    def post(self, request):
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity')
        cart_id = request.data.get('cart')
        customer_id = request.data.get('customer_id')

        if not product_id:
            return Response({"error": "product_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not quantity:
            return Response({"error": "quantity is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Cho phép client chỉ gửi customer_id (không cần cart_id)
        if not cart_id:
            if not customer_id:
                return Response(
                    {"error": "cart hoặc customer_id là bắt buộc"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            cart, _ = Cart.objects.get_or_create(customer_id=customer_id)
            cart_id = cart.id
        
        # Check if product exists in product-service
        try:
            r = requests.get(f"{PRODUCT_SERVICE_URL}/products/{product_id}/", timeout=5)
            if r.status_code != 200:
                return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        except requests.exceptions.RequestException as e:
            return Response({"error": f"Error checking product: {str(e)}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
        serializer = CartItemSerializer(data={"cart": cart_id, "product_id": product_id, "quantity": quantity})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ViewCart(APIView):
    def get(self, request, customer_id):
        try:
            cart = Cart.objects.get(customer_id=customer_id)
            items = CartItem.objects.filter(cart=cart)
            serializer = CartItemSerializer(items, many=True)
            return Response(serializer.data)
        except Cart.DoesNotExist:
            return Response({"error": "Cart not found"}, status=status.HTTP_404_NOT_FOUND)


class UpdateCartItem(APIView):
    def put(self, request, pk):
        try:
            item = CartItem.objects.get(pk=pk)
            serializer = CartItemSerializer(item, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except CartItem.DoesNotExist:
            return Response({"error": "Cart item not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        try:
            item = CartItem.objects.get(pk=pk)
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except CartItem.DoesNotExist:
            return Response({"error": "Cart item not found"}, status=status.HTTP_404_NOT_FOUND)
