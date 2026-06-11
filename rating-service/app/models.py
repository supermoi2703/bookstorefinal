from django.db import models


class Rating(models.Model):
    product_id = models.IntegerField()
    customer_id = models.IntegerField()
    rating = models.IntegerField()  # 1-5 stars
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['product_id', 'customer_id']  # One rating per customer per product

    def __str__(self):
        return f"Rating {self.rating} for product {self.product_id} by customer {self.customer_id}"
