from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Shipping
from .serializers import ShippingSerializer


class ShippingCreate(APIView):
    def post(self, request):
        serializer = ShippingSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ShippingDetail(APIView):
    def get(self, request, pk):
        try:
            shipping = Shipping.objects.get(pk=pk)
            serializer = ShippingSerializer(shipping)
            return Response(serializer.data)
        except Shipping.DoesNotExist:
            return Response({"error": "Shipping not found"}, status=status.HTTP_404_NOT_FOUND)


class ShippingByOrder(APIView):
    """Lấy thông tin shipping theo order_id."""
    def get(self, request, order_id):
        try:
            shipping = Shipping.objects.get(order_id=order_id)
            serializer = ShippingSerializer(shipping)
            return Response(serializer.data)
        except Shipping.DoesNotExist:
            return Response({"error": "Shipping not found"}, status=status.HTTP_404_NOT_FOUND)
