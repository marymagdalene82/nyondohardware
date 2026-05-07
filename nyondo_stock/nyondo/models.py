from django.db import models
from decimal import Decimal
from django.core.exceptions import ValidationError


# Create your models here.
# Category model
class Category(models.Model):
    name = models.CharField(max_length=255)
    is_deposit_allowed = models.BooleanField(default=False)

    def __str__(self):
        return self.name


# Product model
class Product(models.Model):
    product_name = models.CharField(max_length=255)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    variant = models.CharField(max_length=255, blank=True, null=True)
    unit = models.CharField(max_length=50)
    stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # stock_status = models.CharField(max_length=20, default="In Stock")
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    reorder_level = models.IntegerField()
    date_added = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.product_name

    @property
    def stock_status(self):
        if self.stock == 0:
            return "Out of Stock"
        elif self.stock < self.reorder_level:
            return "Low Stock"
        return "In Stock"

    @property
    def eligible_for_deposit(self):
        return self.category.is_deposit_allowed


# Supplier model
class Supplier(models.Model):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=15)
    contact_person = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.name


# StockEntry model
class StockEntry(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)

    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    is_credit = models.BooleanField(default=False)
    amount_paid = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    balance_due = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total(self):
        return self.quantity * self.unit_cost

    def save(self, *args, **kwargs):
        # Do not allow editing of existing entries
        if self.pk is not None:
            raise ValidationError(
                "Stock entries cannot be edited. Create a new entry instead."
            )

        total = self.total

        # credit logic
        if self.is_credit:
            self.balance_due = total - (self.amount_paid or Decimal("0.00"))
        else:
            self.amount_paid = total
            self.balance_due = Decimal("0.00")

        super().save(*args, **kwargs)

        # update product stock + latest prices (creation only)
        self.product.stock += self.quantity
        self.product.unit_cost = self.unit_cost
        self.product.unit_price = self.unit_price
        self.product.save(update_fields=["stock", "unit_cost", "unit_price"])

    def __str__(self):
        return f"{self.product.product_name} - {self.quantity}"
