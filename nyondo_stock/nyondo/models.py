from django.db import models
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator


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


# Models for sale
class Sale(models.Model):
    CUSTOMER_TYPE = [
        ("WHOLESALE", "Wholesaler"),
        ("RETAIL", "Retailer"),
        ("INDIVIDUAL", "Individual Buyer"),
        ("SCHEME", "Deposit Scheme Earner"),
    ]
    customer_name = models.CharField(max_length=255, blank=True)
    customer_type = models.CharField(max_length=20, choices=CUSTOMER_TYPE)
    sale_date = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    distance_km = models.FloatField(default=0)
    transport_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # processed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    def calculate_transport(self):
    # Free transport for 500k+ within 10km
        if self.distance_km and self.distance_km <= 10 and self.total_amount >= Decimal("500000"):
            return Decimal("0.00")
        if self.distance_km and self.distance_km > 0:
            return Decimal("30000.00")
        return Decimal("0.00")


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        self.unit_price = self.product.unit_price
        self.subtotal = self.quantity * self.unit_price

        if is_new:
            if self.product.stock < self.quantity:
                raise ValidationError(
                    f"Not enough stock for {self.product.product_name}"
                )

            self.product.stock -= self.quantity
            self.product.save(update_fields=["stock"])

        super().save(*args, **kwargs)

# Deposit Scheme model
class DepositCustomer(models.Model):
    depost_customer_name = models.CharField(max_length=255)
    nin = models.CharField(max_length=255)
    phone = models.CharField(max_length=15)
    address = models.CharField(max_length=255)
    occupation = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.full_name} ({self.nin})" 

    @property
    def balance(self):
        # Deposits increase balance, pickups decrease it.
        deposits = (
            self.transactions.filter(tx_type="DEPOSIT")
            .aggregate(models.Sum("amount"))
            .get("amount__sum")
            or Decimal("0.00")
        )
        pickups = (
            self.transactions.filter(tx_type="PICKUP")
            .aggregate(models.Sum("amount"))
            .get("amount__sum")
            or Decimal("0.00")
        )
        return deposits - pickups
    
class DepositTransaction(models.Model):
    TX_TYPE_CHOICES = [
        ("DEPOSIT", "Deposit"),
        ("PICKUP", "Pickup"),
    ]
    customer = models.ForeignKey(DepositCustomer, related_name="transactions", on_delete=models.CASCADE)
    tx_type = models.CharField(max_length=10, choices=TX_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tx_type} of {self.amount} for {self.customer.depost_customer_name}"
    
class DepositPickup(models.Model):
    customer = models.ForeignKey(DepositCustomer, on_delete=models.PROTECT, related_name="pickups")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total(self):
        return sum((i.total for i in self.items.all()), Decimal("0.00"))

    def __str__(self):
        return f"Pickup #{self.pk} - {self.customer.full_name}"


class DepositPickupItem(models.Model):
    pickup = models.ForeignKey(DepositPickup, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)

    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def total(self):
        return Decimal(self.quantity) * self.unit_price

    def clean(self):
        # enforce deposit eligibility (category)
        if not self.product.category.is_deposit_allowed:
            raise ValidationError("This product is not eligible for the deposit scheme.")
   


