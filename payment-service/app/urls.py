from django.urls import path
from .views import PaymentCreate, PaymentDetail, PaymentByOrder

urlpatterns = [
    path('payments/', PaymentCreate.as_view()),
    path('payments/<int:pk>/', PaymentDetail.as_view()),
    path('payments/order/<int:order_id>/', PaymentByOrder.as_view()),
]
