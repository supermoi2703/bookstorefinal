from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Customer, CustomerAddress, Wishlist
from .serializers import CustomerSerializer, CustomerProfileSerializer, CustomerAddressSerializer, WishlistSerializer
import requests
import os
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token

CART_SERVICE_URL = os.environ.get('CART_SERVICE_URL', 'http://cart-service:8000')


class CustomerListCreate(APIView):
    def get(self, request):
        customers = Customer.objects.all()
        serializer = CustomerSerializer(customers, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = CustomerSerializer(data=request.data)
        if serializer.is_valid():
            customer = serializer.save()
            try:
                requests.post(
                    f"{CART_SERVICE_URL}/carts/",
                    json={"customer_id": customer.id},
                    timeout=5
                )
            except requests.exceptions.RequestException as e:
                print(f"Error creating cart: {e}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CustomerProfile(APIView):
    """Lấy và cập nhật profile khách hàng."""
    def get(self, request, customer_id):
        try:
            customer = Customer.objects.get(pk=customer_id)
            serializer = CustomerProfileSerializer(customer)
            data = serializer.data
            # Include addresses
            addresses = CustomerAddress.objects.filter(customer=customer)
            data['addresses'] = CustomerAddressSerializer(addresses, many=True).data
            return Response(data)
        except Customer.DoesNotExist:
            return Response({"error": "Customer not found"}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, customer_id):
        try:
            customer = Customer.objects.get(pk=customer_id)
            serializer = CustomerProfileSerializer(customer, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Customer.DoesNotExist:
            return Response({"error": "Customer not found"}, status=status.HTTP_404_NOT_FOUND)


class CustomerAddressListCreate(APIView):
    """CRUD địa chỉ giao hàng."""
    def get(self, request, customer_id):
        addresses = CustomerAddress.objects.filter(customer_id=customer_id)
        serializer = CustomerAddressSerializer(addresses, many=True)
        return Response(serializer.data)

    def post(self, request, customer_id):
        data = request.data.copy()
        data['customer'] = customer_id
        serializer = CustomerAddressSerializer(data=data)
        if serializer.is_valid():
            # Nếu đặt là default, bỏ default của các địa chỉ khác
            if serializer.validated_data.get('is_default'):
                CustomerAddress.objects.filter(customer_id=customer_id).update(is_default=False)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CustomerAddressDetail(APIView):
    def put(self, request, pk):
        try:
            addr = CustomerAddress.objects.get(pk=pk)
            serializer = CustomerAddressSerializer(addr, data=request.data, partial=True)
            if serializer.is_valid():
                if serializer.validated_data.get('is_default'):
                    CustomerAddress.objects.filter(customer=addr.customer).update(is_default=False)
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except CustomerAddress.DoesNotExist:
            return Response({"error": "Address not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        try:
            addr = CustomerAddress.objects.get(pk=pk)
            addr.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except CustomerAddress.DoesNotExist:
            return Response({"error": "Address not found"}, status=status.HTTP_404_NOT_FOUND)


class WishlistListCreate(APIView):
    """Danh sách yêu thích của khách hàng."""
    def get(self, request, customer_id):
        wishlists = Wishlist.objects.filter(customer_id=customer_id).order_by('-created_at')
        serializer = WishlistSerializer(wishlists, many=True)
        return Response(serializer.data)

    def post(self, request, customer_id):
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({"error": "product_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            customer = Customer.objects.get(pk=customer_id)
        except Customer.DoesNotExist:
            return Response({"error": "Customer not found"}, status=status.HTTP_404_NOT_FOUND)

        wishlist, created = Wishlist.objects.get_or_create(customer=customer, product_id=product_id)
        if not created:
            return Response({"message": "Already in wishlist"}, status=status.HTTP_200_OK)
        serializer = WishlistSerializer(wishlist)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class WishlistDelete(APIView):
    """Xóa sách khỏi wishlist."""
    def delete(self, request, customer_id, product_id):
        try:
            wishlist = Wishlist.objects.get(customer_id=customer_id, product_id=product_id)
            wishlist.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Wishlist.DoesNotExist:
            return Response({"error": "Not in wishlist"}, status=status.HTTP_404_NOT_FOUND)


class WishlistCheck(APIView):
    """Kiểm tra sách có trong wishlist không."""
    def get(self, request, customer_id, product_id):
        exists = Wishlist.objects.filter(customer_id=customer_id, product_id=product_id).exists()
        return Response({"in_wishlist": exists})


class Register(APIView):
    def post(self, request):
        name = request.data.get('name')
        email = request.data.get('email')
        password = request.data.get('password')

        if not name or not email or not password:
            return Response({'error': 'name, email, password là bắt buộc'}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=email).exists():
            return Response({'error': 'Email đã tồn tại'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(username=email, email=email, password=password)
        customer = Customer.objects.create(user=user, name=name, email=email)

        cart_id = None
        try:
            cart_resp = requests.post(
                f"{CART_SERVICE_URL}/carts/",
                json={"customer_id": customer.id},
                timeout=5
            )
            if cart_resp.status_code in (200, 201):
                cart_id = cart_resp.json().get("id")
        except requests.exceptions.RequestException as e:
            print(f"Error creating cart: {e}")

        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                'token': token.key,
                'customer_id': customer.id,
                'cart_id': cart_id,
                'email': email,
                'name': name,
            },
            status=status.HTTP_201_CREATED
        )


class Login(APIView):
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({'error': 'email, password là bắt buộc'}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(username=email, password=password)
        if not user:
            return Response({'error': 'Sai email hoặc password'}, status=status.HTTP_401_UNAUTHORIZED)

        token, _ = Token.objects.get_or_create(user=user)
        customer = Customer.objects.filter(user=user).first()
        return Response(
            {
                'token': token.key,
                'customer_id': customer.id if customer else None,
                'is_staff': user.is_staff,
                'name': customer.name if customer else '',
            },
            status=status.HTTP_200_OK
        )
