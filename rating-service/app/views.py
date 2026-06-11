from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Rating
from .serializers import RatingSerializer
import requests
import os

PRODUCT_SERVICE_URL = os.environ.get('PRODUCT_SERVICE_URL', 'http://product-service:8000')


class RatingCreate(APIView):
    def post(self, request):
        product_id = request.data.get('product_id')
        
        # Check if product exists in product-service
        if product_id:
            try:
                r = requests.get(f"{PRODUCT_SERVICE_URL}/products/{product_id}/", timeout=5)
                if r.status_code != 200:
                    return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
            except requests.exceptions.RequestException as e:
                return Response(
                    {"error": f"Error checking product: {str(e)}"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
        
        serializer = RatingSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RatingList(APIView):
    def get(self, request):
        product_id = request.query_params.get('product_id')
        if product_id:
            ratings = Rating.objects.filter(product_id=product_id)
        else:
            ratings = Rating.objects.all()
        
        serializer = RatingSerializer(ratings, many=True)
        return Response(serializer.data)
