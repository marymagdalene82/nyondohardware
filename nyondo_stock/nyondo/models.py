from django.db import models

# Create your models here.
# Product model
class Product(models.Model):
    product_name = models.CharField(max_length=255)
    category = models.CharField(max_length=255)
    variant = models.CharField(max_length=255, blank=True, null=True)
    unit = models.CharField(max_length=50)
    stock = models.IntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    reorder_level = models.IntegerField()
    date_added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.product_name
