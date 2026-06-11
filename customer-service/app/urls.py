from django.urls import path
from .views import (
    CustomerListCreate, Register, Login,
    CustomerProfile,
    CustomerAddressListCreate, CustomerAddressDetail,
    WishlistListCreate, WishlistDelete, WishlistCheck,
)

urlpatterns = [
    path('customers/', CustomerListCreate.as_view()),
    path('auth/register/', Register.as_view()),
    path('auth/login/', Login.as_view()),

    # Profile
    path('customers/<int:customer_id>/profile/', CustomerProfile.as_view()),

    # Addresses
    path('customers/<int:customer_id>/addresses/', CustomerAddressListCreate.as_view()),
    path('addresses/<int:pk>/', CustomerAddressDetail.as_view()),

    # Wishlist
    path('customers/<int:customer_id>/wishlist/', WishlistListCreate.as_view()),
    path('customers/<int:customer_id>/wishlist/<int:product_id>/', WishlistDelete.as_view()),
    path('customers/<int:customer_id>/wishlist/<int:product_id>/check/', WishlistCheck.as_view()),
]
