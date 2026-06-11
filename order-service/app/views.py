from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Order, OrderItem
from .serializers import OrderSerializer, OrderItemSerializer
import requests
import os

CART_SERVICE_URL = os.environ.get('CART_SERVICE_URL', 'http://cart-service:8000')
PAYMENT_SERVICE_URL = os.environ.get('PAYMENT_SERVICE_URL', 'http://payment-service:8000')
SHIPPING_SERVICE_URL = os.environ.get('SHIPPING_SERVICE_URL', 'http://shipping-service:8000')
PRODUCT_SERVICE_URL = os.environ.get('PRODUCT_SERVICE_URL', 'http://product-service:8000')


class OrderCreate(APIView):
    def post(self, request):
        customer_id = request.data.get('customer_id')
        payment_method = request.data.get('payment_method')
        shipping_method = request.data.get('shipping_method')
        address = request.data.get('address', '')
        phone = request.data.get('phone', '')
        
        if not all([customer_id, payment_method, shipping_method]):
            return Response(
                {"error": "customer_id, payment_method, and shipping_method are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get cart items from cart-service
        try:
            cart_response = requests.get(f"{CART_SERVICE_URL}/carts/{customer_id}/", timeout=5)
            if cart_response.status_code != 200:
                return Response({"error": "Cart not found"}, status=status.HTTP_404_NOT_FOUND)
            
            cart_items = cart_response.json()
            if not cart_items:
                return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Get real prices from product-service
            total_amount = 0
            enriched_items = []
            for item in cart_items:
                product_price = 10  # fallback
                try:
                    br = requests.get(f"{PRODUCT_SERVICE_URL}/products/{item['product_id']}/", timeout=5)
                    if br.status_code == 200:
                        product_price = float(br.json().get('price', 10))
                except requests.exceptions.RequestException:
                    pass
                enriched_items.append({
                    'product_id': item['product_id'],
                    'quantity': item['quantity'],
                    'price': product_price,
                })
                total_amount += item['quantity'] * product_price
            
            # Create order
            order = Order.objects.create(
                customer_id=customer_id,
                total_amount=total_amount,
                payment_method=payment_method,
                shipping_method=shipping_method,
                status='pending'
            )
            
            # Create order items
            for item in enriched_items:
                OrderItem.objects.create(
                    order=order,
                    product_id=item['product_id'],
                    quantity=item['quantity'],
                    price=item['price'],
                )
            
            # Trigger payment service
            try:
                payment_data = {
                    'order_id': order.id,
                    'customer_id': customer_id,
                    'amount': str(total_amount),
                    'payment_method': payment_method
                }
                requests.post(f"{PAYMENT_SERVICE_URL}/payments/", json=payment_data, timeout=5)
            except requests.exceptions.RequestException as e:
                print(f"Error creating payment: {e}")
            
            # Trigger shipping service
            try:
                shipping_data = {
                    'order_id': order.id,
                    'customer_id': customer_id,
                    'shipping_method': shipping_method,
                    'address': address,
                    'phone': phone,
                }
                requests.post(f"{SHIPPING_SERVICE_URL}/shippings/", json=shipping_data, timeout=5)
            except requests.exceptions.RequestException as e:
                print(f"Error creating shipping: {e}")
            
            # Clear cart after order
            try:
                cart_items_resp = requests.get(f"{CART_SERVICE_URL}/carts/{customer_id}/", timeout=5)
                if cart_items_resp.status_code == 200:
                    for ci in cart_items_resp.json():
                        requests.delete(f"{CART_SERVICE_URL}/cart-items/{ci['id']}/", timeout=5)
            except requests.exceptions.RequestException as e:
                print(f"Error clearing cart: {e}")
            
            serializer = OrderSerializer(order)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except requests.exceptions.RequestException as e:
            return Response(
                {"error": f"Error fetching cart: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class OrderDetail(APIView):
    def get(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
            serializer = OrderSerializer(order)
            return Response(serializer.data)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)


class OrdersByCustomer(APIView):
    """Lấy danh sách đơn hàng theo customer_id."""
    def get(self, request, customer_id):
        orders = Order.objects.filter(customer_id=customer_id).order_by('-created_at')
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)
