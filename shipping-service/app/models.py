from django.db import models


class Shipping(models.Model):
    order_id = models.IntegerField()
    customer_id = models.IntegerField()
    shipping_method = models.CharField(max_length=50)
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    status = models.CharField(max_length=50, default='pending')
    tracking_number = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Shipping {self.id} for order {self.order_id}"
