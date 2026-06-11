from django.urls import path
from .views import ShippingCreate, ShippingDetail, ShippingByOrder

urlpatterns = [
    path('shippings/', ShippingCreate.as_view()),
    path('shippings/<int:pk>/', ShippingDetail.as_view()),
    path('shippings/order/<int:order_id>/', ShippingByOrder.as_view()),
]
