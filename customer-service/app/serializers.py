from rest_framework import serializers
from .models import Customer, CustomerAddress, Wishlist


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'


class CustomerProfileSerializer(serializers.ModelSerializer):
    """Serializer cho cập nhật profile (không cho sửa email, user)."""
    class Meta:
        model = Customer
        fields = ['id', 'name', 'email', 'phone', 'address', 'date_of_birth', 'gender', 'avatar_url', 'created_at', 'updated_at']
        read_only_fields = ['id', 'email', 'created_at', 'updated_at']


class CustomerAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerAddress
        fields = '__all__'


class WishlistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wishlist
        fields = '__all__'
