from django.urls import path
from .views import (
    ProductListCreate, ProductDetail, ProductSearch, FeaturedProducts,
    CategoryListCreate, CategoryDetail,
)

urlpatterns = [
    path('products/', ProductListCreate.as_view()),
    path('products/<int:pk>/', ProductDetail.as_view()),
    path('products/search/', ProductSearch.as_view()),
    path('products/featured/', FeaturedProducts.as_view()),
    path('categories/', CategoryListCreate.as_view()),
    path('categories/<int:pk>/', CategoryDetail.as_view()),
]
