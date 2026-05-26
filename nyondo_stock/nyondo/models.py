from django.db import models
from django.core.validators import RegexValidator
from django.contrib.auth import get_user_model

User = get_user_model()

phone_validator = RegexValidator(
    regex=r"^(\+256|0)7\d{8}$",
    message="Enter a valid Ugandan number: 07XXXXXXXXX or +2567XXXXXXXX",
)

# 14 characters total: CM/CF + 12 alphanumeric
nin_validator = RegexValidator(
    regex=r"^(CM|CF)[A-Z0-9]{12}$",
    message="NIN must be 14 characters and start with CM or CF.",
)


class Category(models.Model):
    name = models.CharField(max_length=255)
    is_deposit_allowed = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Product(models.Model):
    UNIT = [
        ("PIECE", "Piece"),
        ("KILOGRAM", "Kilogram"),
        ("BAG", "Bag"),
        ("METER", "Meter"),
        ("ROLL", "Roll"),
    ]
    product_name = models.CharField(max_length=255)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    variant = models.CharField(max_length=255, blank=True, null=True)
    unit = models.CharField(max_length=50, choices=UNIT)
    stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    reorder_level = models.IntegerField()
    date_added = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.product_name


class Supplier(models.Model):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=15)  # validate in views
    contact_person = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.name


class StockEntry(models.Model):
    PRODUCT_CHOICES = [
        ("1 inc", "1 inc"),
        ("3 inc", "3 inc"),
        ("4 inc", "4 inc"),
        ("5 inc", "5 inc"),
        ("CEM IIIN", "CEM IIIN"),
        ("CEM IIN", "CEM IIN"),
        ("High tensile", "High tensile"),
        ("Low tensile", "Low tensile"),
        ("Roofing nails", "Roofing nails"),
        ("Wheelbarrows", "Wheelbarrows"),
        ("Wire mesh", "Wire mesh"),
    ]
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, choices=PRODUCT_CHOICES
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    is_credit = models.BooleanField(default=False)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.product_name} - {self.quantity}"


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

    processed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="sales"
    )

    def __str__(self):
        return f"Sale #{self.pk}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)

    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.product.product_name} x {self.quantity}"


class DepositCustomer(models.Model):
    full_name = models.CharField(max_length=255)

    nin = models.CharField(max_length=255, validators=[nin_validator], unique=True)
    phone = models.CharField(max_length=15, validators=[phone_validator])
    address = models.CharField(max_length=255)
    occupation = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} ({self.nin})"


class DepositPickup(models.Model):
    customer = models.ForeignKey(
        DepositCustomer, on_delete=models.PROTECT, related_name="pickups"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pickup #{self.pk} - {self.customer.full_name}"


class DepositTransaction(models.Model):
    TX_TYPE_CHOICES = [
        ("DEPOSIT", "Deposit"),
        ("PICKUP", "Pickup"),
    ]

    customer = models.ForeignKey(
        DepositCustomer, related_name="transactions", on_delete=models.CASCADE
    )
    tx_type = models.CharField(max_length=10, choices=TX_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    related_pickup = models.ForeignKey(
        DepositPickup, on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return f"{self.tx_type} of {self.amount} for {self.customer.full_name}"


class DepositPickupItem(models.Model):
    pickup = models.ForeignKey(
        DepositPickup, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT)

    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.product.product_name} x {self.quantity}"
