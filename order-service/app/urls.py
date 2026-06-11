from django.urls import path
from .views import OrderCreate, OrderDetail, OrdersByCustomer

urlpatterns = [
    path('orders/', OrderCreate.as_view()),
    path('orders/<int:pk>/', OrderDetail.as_view()),
    path('orders/customer/<int:customer_id>/', OrdersByCustomer.as_view()),
]
