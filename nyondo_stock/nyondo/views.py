import re
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction, models
from django.db.models import Sum, Count, Q, F, DecimalField, ExpressionWrapper
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    Product,
    Category,
    StockEntry,
    Supplier,
    Sale,
    SaleItem,
    DepositCustomer,
    DepositTransaction,
    DepositPickup,
    DepositPickupItem,
)

User = get_user_model()


# AUTH GUARD (NO DECORATORS)
def must_login(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return None


# VALIDATION HELPERS
UG_PHONE_RE = re.compile(r"^(\+256|0)7\d{8}$")
UG_NIN_RE = re.compile(r"^(CM|CF)[A-Z0-9]{12}$")  # 14 chars total


def clean_text(raw):
    return (raw or "").strip()


def require_text(raw, label):
    decimal_value = clean_text(raw)
    if not decimal_value:
        raise ValidationError(f"{label} is required.")
    return decimal_value


def parse_decimal(raw, label) -> Decimal:
    raw = clean_text(raw)
    if raw == "":
        raise ValidationError(f"{label} is required.")
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValidationError(f"{label} must be a valid number.")


def require_positive_decimal(raw, label) -> Decimal:
    decimal_value = parse_decimal(raw, label)
    if decimal_value <= 0:
        raise ValidationError(f"{label} must be greater than 0.")
    return decimal_value


def parse_int(raw, label):
    raw = clean_text(raw)
    if raw == "":
        raise ValidationError(f"{label} is required.")
    try:
        return int(raw)
    except ValueError:
        raise ValidationError(f"{label} must be a whole number.")


def require_positive_int(raw, label):
    decimal_value = parse_int(raw, label)
    if decimal_value <= 0:
        raise ValidationError(f"{label} must be greater than 0.")
    return decimal_value


def validate_ug_phone(raw):
    phone = clean_text(raw)
    if not phone:
        raise ValidationError("Phone number is required.")
    if not UG_PHONE_RE.match(phone):
        raise ValidationError(
            "Enter a valid Ugandan number: 07XXXXXXXXX or +2567XXXXXXXX."
        )
    return phone


def validate_nin(raw):
    nin = clean_text(raw).upper()
    if not nin:
        raise ValidationError("NIN is required.")
    if not UG_NIN_RE.match(nin):
        raise ValidationError("NIN must be 14 characters and start with CM or CF.")
    return nin


# -----------------------------
# BUSINESS CALCULATIONS (VIEWS)
# -----------------------------
def calc_stock_status(stock, reorder_level) -> str:
    # stock is Decimal, reorder_level is int
    if stock == 0:
        return "Out of Stock"
    if stock < reorder_level:
        return "Low Stock"
    return "In Stock"

def calc_transport(items_total: Decimal, distance_km: float) -> Decimal:
    # Free transport for 500k+ within 10km
    if distance_km and distance_km <= 10 and items_total >= Decimal("500000"):
        return Decimal("0.00")
    if distance_km and distance_km > 0:
        return Decimal("30000.00")
    return Decimal("0.00")


def calc_deposit_balance(customer: DepositCustomer) -> Decimal:
    deposits = customer.transactions.filter(tx_type="DEPOSIT").aggregate(
        s=Sum("amount")
    )["s"] or Decimal("0.00")
    pickups = customer.transactions.filter(tx_type="PICKUP").aggregate(s=Sum("amount"))[
        "s"
    ] or Decimal("0.00")
    return deposits - pickups


# -----------------------------
# AUTH VIEWS
# -----------------------------
def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = clean_text(request.POST.get("username"))
        password = request.POST.get("password") or ""

        if not username or not password:
            return render(
                request, "login.html", {"error": "Username and password are required."}
            )

        user = authenticate(request, username=username, password=password)
        if user is None:
            return render(
                request, "login.html", {"error": "Invalid username or password."}
            )

        login(request, user)
        return redirect("dashboard")

    return render(request, "login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


# -----------------------------
# DASHBOARD + REPORTS
# -----------------------------
def dashboard(request):
    r = must_login(request)
    if r:
        return r

    today = timezone.localdate()

    sales_today = Sale.objects.filter(sale_date__date=today)
    sales_today_summary = sales_today.aggregate(
        count=Count("id"),
        total=Sum("total_amount"),
        transport=Sum("transport_charge"),
    )

    items_today_qty = (
        SaleItem.objects.filter(sale__sale_date__date=today).aggregate(
            qty=Sum("quantity")
        )["qty"]
        or 0
    )

    low_stock = Product.objects.filter(
        stock__gt=0, stock__lt=F("reorder_level")
    ).order_by("stock")[:10]
    out_of_stock = Product.objects.filter(stock__lte=0).order_by("product_name")[:10]

    supplier_credit_total = StockEntry.objects.filter(is_credit=True).aggregate(
        total=Sum("balance_due")
    )["total"] or Decimal("0.00")

    deposit_customers = DepositCustomer.objects.all()
    total_deposit_balance = sum(
        (calc_deposit_balance(c) for c in deposit_customers), Decimal("0.00")
    )

    deposit_today = DepositTransaction.objects.filter(
        tx_type="DEPOSIT", created_at__date=today
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    pickup_today = DepositTransaction.objects.filter(
        tx_type="PICKUP", created_at__date=today
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    context = {
        "today": today,
        "sales_today_count": sales_today_summary["count"] or 0,
        "sales_today_total": sales_today_summary["total"] or Decimal("0.00"),
        "transport_today_total": sales_today_summary["transport"] or Decimal("0.00"),
        "items_today_qty": items_today_qty,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
        "supplier_credit_total": supplier_credit_total,
        "total_deposit_balance": total_deposit_balance,
        "deposit_today": deposit_today,
        "pickup_today": pickup_today,
    }
    return render(request, "dashboard.html", context)


def report_sales_summary(request):
    r = must_login(request)
    if r:
        return r

    date_from = clean_text(request.GET.get("date_from"))
    date_to = clean_text(request.GET.get("date_to"))
    customer_type = clean_text(request.GET.get("customer_type"))

    query_set = Sale.objects.all().order_by("-sale_date")
    if date_from:
        query_set = query_set.filter(sale_date__date__gte=date_from)
    if date_to:
        query_set = query_set.filter(sale_date__date__lte=date_to)
    if customer_type:
        query_set = query_set.filter(customer_type=customer_type)

    summary = query_set.aggregate(
        count=Count("id"),
        total=Sum("total_amount"),
        transport=Sum("transport_charge"),
    )

    return render(
        request,
        "report_sales_summary.html",
        {
            "sales": query_set[:200],
            "summary": summary,
            "date_from": date_from,
            "date_to": date_to,
            "customer_type": customer_type,
            "customer_types": Sale.CUSTOMER_TYPE,
        },
    )


def report_product_sales(request):
    r = must_login(request)
    if r:
        return r

    date_from = clean_text(request.GET.get("date_from"))
    date_to = clean_text(request.GET.get("date_to"))

    items = SaleItem.objects.select_related("product", "sale")
    if date_from:
        items = items.filter(sale__sale_date__date__gte=date_from)
    if date_to:
        items = items.filter(sale__sale_date__date__lte=date_to)

    revenue_expr = ExpressionWrapper(
        F("quantity") * F("unit_price"), output_field=DecimalField()
    )

    rows = (
        items.values("product__id", "product__product_name")
        .annotate(qty=Sum("quantity"), revenue=Sum(revenue_expr))
        .order_by("-revenue", "-qty", "product__product_name")
    )

    totals = rows.aggregate(
        total_qty=Sum("qty"),
        total_revenue=Sum("revenue"),
    )

    return render(
        request,
        "report_product_sales.html",
        {
            "rows": rows,
            "totals": totals,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


def report_stock_levels(request):
    r = must_login(request)
    if r:
        return r

    low_only = request.GET.get("low_only") == "1"
    query_set = (
        Product.objects.select_related("category").all().order_by("product_name")
    )

    if low_only:
        query_set = query_set.filter(stock__lt=F("reorder_level"))

    return render(
        request,
        "report_stock_levels.html",
        {"products": query_set, "low_only": low_only},
    )


def report_deposit_summary(request):
    r = must_login(request)
    if r:
        return r

    date_from = clean_text(request.GET.get("date_from"))
    date_to = clean_text(request.GET.get("date_to"))

    txs = (
        DepositTransaction.objects.select_related("customer")
        .all()
        .order_by("-created_at")
    )
    if date_from:
        txs = txs.filter(created_at__date__gte=date_from)
    if date_to:
        txs = txs.filter(created_at__date__lte=date_to)

    deposits_total = txs.filter(tx_type="DEPOSIT").aggregate(total=Sum("amount"))[
        "total"
    ] or Decimal("0.00")
    pickups_total = txs.filter(tx_type="PICKUP").aggregate(total=Sum("amount"))[
        "total"
    ] or Decimal("0.00")

    return render(
        request,
        "report_deposit_summary.html",
        {
            "txs": txs[:300],
            "date_from": date_from,
            "date_to": date_to,
            "deposits_total": deposits_total,
            "pickups_total": pickups_total,
            "net_change": deposits_total - pickups_total,
        },
    )


# -----------------------------
# PRODUCTS
# -----------------------------
def product_list(request):
    r = must_login(request)
    if r:
        return r

    q = clean_text(request.GET.get("q"))

    products = Product.objects.select_related("category").all()

    if q:
        products = products.filter(
            Q(product_name__icontains=q) |
            Q(variant__icontains=q) |
            Q(category__name__icontains=q)
        )

    products = products.order_by("product_name")

    totals = products.aggregate(
        total_products=Count("id"),
        total_quantity=Sum("stock"),
        stock_value=Sum(F("stock") * F("unit_cost"), output_field=DecimalField()),
        low_stock_items=Count("id", filter=Q(stock__gt=0, stock__lt=F("reorder_level"))),
        out_of_stock_items=Count("id", filter=Q(stock__lte=0)),
    )
    for k in totals:
        totals[k] = totals[k] or 0

    product_rows = []
    for p in products:
        product_rows.append({
            "product": p,
            "stock_status": calc_stock_status(p.stock, p.reorder_level),
        })

    return render(request, "list.html", {
        "q": q,
        "totals": totals,
        "product_rows": product_rows,
    })

def product_create(request):
    r = must_login(request)
    if r:
        return r

    categories = Category.objects.all().order_by("name")

    if request.method == "POST":
        errors = {}

        product_name = clean_text(request.POST.get("product_name"))
        category_id = clean_text(request.POST.get("category"))
        variant = clean_text(request.POST.get("variant")) or None
        unit = clean_text(request.POST.get("unit"))

        if not product_name:
            errors["product_name"] = "Product name is required."
        if not category_id:
            errors["category"] = "Category is required."
        if not unit:
            errors["unit"] = "Unit is required."

        try:
            unit_cost = require_positive_decimal(
                request.POST.get("unit_cost"), "Unit cost"
            )
        except ValidationError as e:
            errors["unit_cost"] = str(e)
            unit_cost = None

        try:
            unit_price = require_positive_decimal(
                request.POST.get("unit_price"), "Unit price"
            )
        except ValidationError as e:
            errors["unit_price"] = str(e)
            unit_price = None

        try:
            reorder_level = require_positive_int(
                request.POST.get("reorder_level"), "Reorder level"
            )
        except ValidationError as e:
            errors["reorder_level"] = str(e)
            reorder_level = None

        if unit_cost is not None and unit_price is not None and unit_price <= unit_cost:
            errors["unit_price"] = "Selling price must be greater than cost price."

        if errors:
            messages.error(request, "Please correct the errors below.")
            return render(
                request,
                "add_product.html",
                {
                    "categories": categories,
                    "errors": errors,
                    "form_data": request.POST,
                },
            )

        Product.objects.create(
            product_name=product_name,
            category_id=category_id,
            variant=variant,
            unit=unit,
            unit_cost=unit_cost,
            unit_price=unit_price,
            reorder_level=reorder_level,
        )
        messages.success(request, "Product added successfully!")
        return redirect("add_product")

    return render(request, "add_product.html", {"categories": categories})


def product_edit(request, pk):
    r = must_login(request)
    if r:
        return r

    product = get_object_or_404(Product, pk=pk)
    categories = Category.objects.all().order_by("name")

    if request.method == "POST":
        errors = {}

        product_name = clean_text(request.POST.get("product_name"))
        category_id = clean_text(request.POST.get("category"))
        variant = clean_text(request.POST.get("variant")) or None
        unit = clean_text(request.POST.get("unit"))

        if not product_name:
            errors["product_name"] = "Product name is required."
        if not category_id:
            errors["category"] = "Category is required."
        if not unit:
            errors["unit"] = "Unit is required."

        try:
            unit_cost = require_positive_decimal(
                request.POST.get("unit_cost"), "Unit cost"
            )
        except ValidationError as e:
            errors["unit_cost"] = str(e)
            unit_cost = None

        try:
            unit_price = require_positive_decimal(
                request.POST.get("unit_price"), "Unit price"
            )
        except ValidationError as e:
            errors["unit_price"] = str(e)
            unit_price = None

        try:
            reorder_level = require_positive_int(
                request.POST.get("reorder_level"), "Reorder level"
            )
        except ValidationError as e:
            errors["reorder_level"] = str(e)
            reorder_level = None

        if unit_cost is not None and unit_price is not None and unit_price <= unit_cost:
            errors["unit_price"] = "Selling price must be greater than cost price."

        if errors:
            messages.error(request, "Please correct the errors below.")
            return render(
                request,
                "product_edit.html",
                {
                    "product": product,
                    "categories": categories,
                    "errors": errors,
                    "form_data": request.POST,
                },
            )

        product.product_name = product_name
        product.category_id = category_id
        product.variant = variant
        product.unit = unit
        product.unit_cost = unit_cost
        product.unit_price = unit_price
        product.reorder_level = reorder_level
        product.save()

        messages.success(request, "Product updated successfully!")
        return redirect("product_list")

    return render(
        request, "product_edit.html", {"product": product, "categories": categories}
    )


def product_delete(request, pk):
    r = must_login(request)
    if r:
        return r

    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        product.delete()
        messages.success(request, "Product deleted.")
        return redirect("product_list")
    return render(request, "product_confirm_delete.html", {"product": product})


def product_detail(request, pk):
    r = must_login(request)
    if r:
        return r

    product = get_object_or_404(Product.objects.select_related("category"), pk=pk)
    recent_entries = (
        StockEntry.objects.select_related("supplier")
        .filter(product=product)
        .order_by("-created_at")[:10]
    )
    return render(
        request,
        "product_detail.html",
        {"product": product, "recent_entries": recent_entries},
    )


# -----------------------------
# STOCK ENTRIES
# -----------------------------
def add_stock(request):
    r = must_login(request)
    if r:
        return r

    products = Product.objects.all().order_by("product_name")
    suppliers = Supplier.objects.all().order_by("name")

    if request.method == "POST":
        errors = {}

        product_id = clean_text(request.POST.get("product"))
        supplier_id = clean_text(request.POST.get("supplier"))
        is_credit = request.POST.get("is_credit") == "True"

        if not product_id:
            errors["product"] = "Product is required."
        if not supplier_id:
            errors["supplier"] = "Supplier is required."

        try:
            quantity = require_positive_decimal(
                request.POST.get("quantity"), "Quantity"
            )
        except ValidationError as e:
            errors["quantity"] = str(e)
            quantity = None

        try:
            unit_cost = require_positive_decimal(
                request.POST.get("unit_cost"), "Unit cost"
            )
        except ValidationError as e:
            errors["unit_cost"] = str(e)
            unit_cost = None

        try:
            unit_price = require_positive_decimal(
                request.POST.get("unit_price"), "Unit price"
            )
        except ValidationError as e:
            errors["unit_price"] = str(e)
            unit_price = None

        # amount_paid: for credit can be 0; must never be negative
        amount_paid_raw = clean_text(request.POST.get("amount_paid"))
        if amount_paid_raw == "":
            amount_paid = Decimal("0.00")
        else:
            try:
                amount_paid = Decimal(amount_paid_raw)
            except (InvalidOperation, ValueError):
                errors["amount_paid"] = "Amount paid must be a valid number."
                amount_paid = None

        if amount_paid is not None and amount_paid < 0:
            errors["amount_paid"] = "Amount paid cannot be negative."

        if unit_cost is not None and unit_price is not None and unit_price <= unit_cost:
            errors["unit_price"] = "Selling price must be greater than cost price."

        if errors:
            messages.error(request, "Please correct the errors below.")
            return render(
                request,
                "stock_entry_form.html",
                {
                    "products": products,
                    "suppliers": suppliers,
                    "errors": errors,
                    "form_data": request.POST,
                },
            )

        product = get_object_or_404(Product, pk=product_id)

        total_value = quantity * unit_cost

        if is_credit:
            if amount_paid > total_value:
                amount_paid = total_value
            balance_due = total_value - amount_paid
        else:
            amount_paid = total_value
            balance_due = Decimal("0.00")

        with transaction.atomic():
            StockEntry.objects.create(
                product_id=product_id,
                supplier_id=supplier_id,
                quantity=quantity,
                unit_cost=unit_cost,
                unit_price=unit_price,
                is_credit=is_credit,
                amount_paid=amount_paid,
                balance_due=balance_due,
            )

            Product.objects.filter(pk=product.pk).update(
                stock=F("stock") + quantity,
                unit_cost=unit_cost,
                unit_price=unit_price,
            )

        messages.success(request, "Stock arrival recorded.")
        return redirect("stock_entry_list")

    return render(
        request, "stock_entry_form.html", {"products": products, "suppliers": suppliers}
    )


def stock_entry_list(request):
    r = must_login(request)
    if r:
        return r

    entries = StockEntry.objects.select_related("product", "supplier").order_by(
        "-created_at"
    )
    credit_only = request.GET.get("credit_only") == "1"
    if credit_only:
        entries = entries.filter(is_credit=True, balance_due__gt=0)

    totals = entries.aggregate(
        entries_count=Count("id"),
        total_quantity=Sum("quantity"),
        total_value=Sum(F("quantity") * F("unit_cost"), output_field=DecimalField()),
        total_paid=Sum("amount_paid"),
        total_balance=Sum("balance_due"),
    )
    for k in totals:
        totals[k] = totals[k] or 0

    return render(
        request,
        "stock_entry_list.html",
        {"entries": entries, "credit_only": credit_only, "totals": totals},
    )


def stock_entry_detail(request, pk):
    r = must_login(request)
    if r:
        return r
    entry = get_object_or_404(
        StockEntry.objects.select_related("product", "supplier"), pk=pk
    )
    total_value = entry.quantity * entry.unit_cost
    return render(
        request, "stock_entry_detail.html", {"entry": entry, "total_value": total_value}
    )


def stock_entry_pay(request, pk):
    r = must_login(request)
    if r:
        return r

    entry = get_object_or_404(
        StockEntry.objects.select_related("product", "supplier"), pk=pk
    )

    if request.method == "POST":
        errors = {}

        try:
            pay_amount = require_positive_decimal(
                request.POST.get("pay_amount"), "Payment amount"
            )
        except ValidationError as e:
            errors["pay_amount"] = str(e)
            pay_amount = None

        if entry.balance_due <= 0:
            errors["pay_amount"] = "This entry has no balance due."

        if pay_amount is not None and pay_amount > entry.balance_due:
            pay_amount = entry.balance_due  # clamp

        if errors:
            messages.error(request, "Please correct the errors below.")
            return render(
                request,
                "stock_entry_pay.html",
                {"entry": entry, "errors": errors, "form_data": request.POST},
            )

        new_paid = entry.amount_paid + pay_amount
        new_balance = entry.balance_due - pay_amount

        StockEntry.objects.filter(pk=entry.pk).update(
            amount_paid=new_paid,
            balance_due=new_balance,
            is_credit=new_balance > 0,
        )

        messages.success(request, "Payment recorded.")
        return redirect("stock_entry_list")

    return render(request, "stock_entry_pay.html", {"entry": entry})


# -----------------------------
# SALES
# -----------------------------
def sale_list(request):
    r = must_login(request)
    if r:
        return r

    sales = Sale.objects.prefetch_related("items").all().order_by("-sale_date")
    totals = sales.aggregate(
        sales_count=Count("id"),
        total_revenue=Sum("total_amount"),
        transport_total=Sum("transport_charge"),
    )
    for k in totals:
        totals[k] = totals[k] or 0
    return render(request, "sale_list.html", {"sales": sales, "totals": totals})


def sale_detail(request, pk):
    r = must_login(request)
    if r:
        return r
    sale = get_object_or_404(Sale.objects.prefetch_related("items__product"), pk=pk)
    return render(request, "sale_detail.html", {"sale": sale})


def sale_create(request):
    r = must_login(request)
    if r:
        return r

    products = Product.objects.all().order_by("product_name")

    if request.method == "POST":
        errors = {}

        customer_name = clean_text(request.POST.get("customer_name"))
        customer_type = clean_text(request.POST.get("customer_type"))
        if not customer_type:
            errors["customer_type"] = "Customer type is required."

        # distance can be 0; but cannot be negative
        dist_raw = clean_text(request.POST.get("distance_km"))
        if dist_raw == "":
            distance_km = 0.0
        else:
            try:
                distance_km = float(dist_raw)
                if distance_km < 0:
                    errors["distance_km"] = "Distance cannot be negative."
            except ValueError:
                errors["distance_km"] = "Distance must be a valid number."
                distance_km = 0.0

        product_ids = request.POST.getlist("product[]")
        qty_list = request.POST.getlist("quantity[]")

        if not product_ids or not qty_list or len(product_ids) != len(qty_list):
            errors["items"] = "Please add at least one product with quantity."

        line_items = []
        if "items" not in errors:
            for pid, qty_raw in zip(product_ids, qty_list):
                pid = clean_text(pid)
                qty_raw = clean_text(qty_raw)

                if not pid:
                    continue

                try:
                    qty = require_positive_int(qty_raw, "Quantity")
                except ValidationError as e:
                    errors["items"] = str(e)
                    break

                product = get_object_or_404(Product, pk=pid)

                if product.stock < qty:
                    errors["items"] = (
                        f"Not enough stock for {product.product_name}. Available: {product.stock}"
                    )
                    break

                unit_price = product.unit_price
                if unit_price <= 0:
                    errors["items"] = f"Invalid unit price for {product.product_name}."
                    break

                subtotal = Decimal(qty) * unit_price
                line_items.append((product, qty, unit_price, subtotal))

            if not line_items and "items" not in errors:
                errors["items"] = "Please add at least one product."

        if errors:
            messages.error(request, "Please correct the errors below.")
            return render(
                request,
                "create_sale.html",
                {
                    "products": products,
                    "errors": errors,
                    "form_data": request.POST,
                },
            )

        with transaction.atomic():
            sale = Sale.objects.create(
                customer_name=customer_name,
                customer_type=customer_type,
                distance_km=distance_km,
                total_amount=Decimal("0.00"),
                transport_charge=Decimal("0.00"),
                processed_by=request.user,
            )

            items_total = Decimal("0.00")

            for product, qty, unit_price, subtotal in line_items:
                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=qty,
                    unit_price=unit_price,
                    subtotal=subtotal,
                )
                Product.objects.filter(pk=product.pk).update(stock=F("stock") - qty)
                items_total += subtotal

            transport = calc_transport(items_total, distance_km)
            grand_total = items_total + transport

            Sale.objects.filter(pk=sale.pk).update(
                transport_charge=transport,
                total_amount=grand_total,
            )

        messages.success(request, "Sale created successfully!")
        return redirect("sale_detail", pk=sale.pk)

    return render(request, "create_sale.html", {"products": products})


def sale_receipt(request, pk):
    r = must_login(request)
    if r:
        return r
    sale = get_object_or_404(Sale.objects.prefetch_related("items__product"), pk=pk)
    return render(request, "receipt.html", {"sale": sale})


# -----------------------------
# DEPOSITS
# -----------------------------
def deposit_customer_list(request):
    r = must_login(request)
    if r:
        return r

    q = clean_text(request.GET.get("q"))
    customers = DepositCustomer.objects.all().order_by("-id")
    if q:
        customers = customers.filter(
            models.Q(full_name__icontains=q)
            | models.Q(nin__icontains=q)
            | models.Q(phone__icontains=q)
        )

    # If templates used customer.balance before, compute balances here
    customer_rows = [{"obj": c, "balance": calc_deposit_balance(c)} for c in customers]

    return render(
        request,
        "deposit_customer_list.html",
        {
            "customers": customers,
            "customer_rows": customer_rows,
            "q": q,
        },
    )


def deposit_customer_create(request):
    r = must_login(request)
    if r:
        return r

    if request.method == "POST":
        errors = {}

        full_name = clean_text(request.POST.get("full_name"))
        address = clean_text(request.POST.get("address"))
        occupation = clean_text(request.POST.get("occupation"))

        if not full_name:
            errors["full_name"] = "Full name is required."
        if not address:
            errors["address"] = "Address is required."
        if not occupation:
            errors["occupation"] = "Occupation is required."

        try:
            nin = validate_nin(request.POST.get("nin"))
        except ValidationError as e:
            errors["nin"] = str(e)
            nin = None

        try:
            phone = validate_ug_phone(request.POST.get("phone"))
        except ValidationError as e:
            errors["phone"] = str(e)
            phone = None

        if nin and DepositCustomer.objects.filter(nin=nin).exists():
            errors["nin"] = "This NIN is already registered."

        if errors:
            messages.error(request, "Please correct the errors below.")
            return render(
                request,
                "deposit_customer_form.html",
                {"errors": errors, "form_data": request.POST},
            )

        customer = DepositCustomer.objects.create(
            full_name=full_name,
            nin=nin,
            phone=phone,
            address=address,
            occupation=occupation,
        )
        messages.success(request, "Deposit customer registered.")
        return redirect("deposit_customer_detail", pk=customer.pk)

    return render(request, "deposit_customer_form.html")


def deposit_customer_detail(request, pk):
    r = must_login(request)
    if r:
        return r

    customer = get_object_or_404(DepositCustomer, pk=pk)
    transactions = customer.transactions.order_by("-created_at")[:20]
    pickups = customer.pickups.order_by("-created_at")[:10]
    balance = calc_deposit_balance(customer)

    return render(
        request,
        "deposit_customer_detail.html",
        {
            "customer": customer,
            "transactions": transactions,
            "pickups": pickups,
            "balance": balance,
        },
    )


def deposit_make(request, pk):
    r = must_login(request)
    if r:
        return r

    customer = get_object_or_404(DepositCustomer, pk=pk)

    if request.method == "POST":
        errors = {}

        try:
            amount = require_positive_decimal(
                request.POST.get("amount"), "Deposit amount"
            )
        except ValidationError as e:
            errors["amount"] = str(e)
            amount = None

        notes = clean_text(request.POST.get("notes"))

        if errors:
            messages.error(request, "Please correct the errors below.")
            balance = calc_deposit_balance(customer)
            return render(
                request,
                "deposit_make.html",
                {
                    "customer": customer,
                    "balance": balance,
                    "errors": errors,
                    "form_data": request.POST,
                },
            )

        tx = DepositTransaction.objects.create(
            customer=customer,
            tx_type="DEPOSIT",
            amount=amount,
            notes=notes,
        )
        messages.success(request, "Deposit recorded.")
        return redirect("deposit_receipt", pk=tx.pk)
    balance = calc_deposit_balance(customer)
    return render(
        request, "deposit_make.html", {"customer": customer, "balance": balance}
    )


def deposit_receipt(request, pk):
    r = must_login(request)
    if r:
        return r

    tx = get_object_or_404(
        DepositTransaction.objects.select_related("customer"),
        pk=pk,
        tx_type="DEPOSIT",
    )
    return render(request, "deposit_receipt.html", {"tx": tx})


def deposit_pickup_create(request, pk):
    r = must_login(request)
    if r:
        return r

    customer = get_object_or_404(DepositCustomer, pk=pk)
    products = (
        Product.objects.select_related("category")
        .filter(category__is_deposit_allowed=True)
        .order_by("product_name")
    )

    if request.method == "POST":
        errors = {}

        product_id = clean_text(request.POST.get("product"))
        if not product_id:
            errors["product"] = "Select a product."

        try:
            quantity = require_positive_int(request.POST.get("quantity"), "Quantity")
        except ValidationError as e:
            errors["quantity"] = str(e)
            quantity = None

        if errors:
            messages.error(request, "Please correct the errors below.")
            return render(
                request,
                "deposit_pickup_form.html",
                {
                    "customer": customer,
                    "products": products,
                    "errors": errors,
                    "form_data": request.POST,
                },
            )

        product = get_object_or_404(
            Product.objects.select_related("category"), pk=product_id
        )

        if not product.category.is_deposit_allowed:
            errors["product"] = "This product is not eligible for the deposit scheme."

        if product.stock < quantity:
            errors["quantity"] = f"Not enough stock. Available: {product.stock}"

        unit_price = product.unit_price
        if unit_price <= 0:
            errors["product"] = "This product has invalid price."

        total_cost = Decimal(quantity) * unit_price
        balance = calc_deposit_balance(customer)

        if total_cost <= 0:
            errors["quantity"] = "Total pickup cost must be greater than 0."

        if balance < total_cost:
            errors["quantity"] = (
                f"Insufficient deposit balance. Balance: UGX {balance}. Required: UGX {total_cost}."
            )

        if errors:
            messages.error(request, "Please correct the errors below.")
            balance = calc_deposit_balance(customer)
            return render(
                request,
                "deposit_pickup_form.html",
                {
                    "customer": customer,
                    "products": products,
                    "balance": balance,
                    "errors": errors,
                    "form_data": request.POST,
                },
            )

        with transaction.atomic():
            pickup = DepositPickup.objects.create(customer=customer)

            DepositPickupItem.objects.create(
                pickup=pickup,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
            )

            Product.objects.filter(pk=product.pk).update(stock=F("stock") - quantity)

            DepositTransaction.objects.create(
                customer=customer,
                tx_type="PICKUP",
                amount=total_cost,
                notes=f"Pickup #{pickup.pk}",
                related_pickup=pickup,
            )

        messages.success(request, "Pickup recorded.")
        return redirect("deposit_pickup_receipt", pk=pickup.pk)
    balance = calc_deposit_balance(customer)
    return render(
        request,
        "deposit_pickup_form.html",
        {"customer": customer, "products": products, "balance": balance},
    )


def deposit_pickup_receipt(request, pk):
    r = must_login(request)
    if r:
        return r

    pickup = get_object_or_404(
        DepositPickup.objects.select_related("customer").prefetch_related(
            "items__product"
        ),
        pk=pk,
    )

    total = sum(
        (Decimal(i.quantity) * i.unit_price for i in pickup.items.all()),
        Decimal("0.00"),
    )

    return render(
        request, "deposit_pickup_receipt.html", {"pickup": pickup, "total": total}
    )


# -----------------------------
# SUPPLIERS
# -----------------------------
def supplier_list(request):
    r = must_login(request)
    if r:
        return r

    q = clean_text(request.GET.get("q"))
    suppliers = Supplier.objects.all().order_by("name")
    if q:
        suppliers = suppliers.filter(
            models.Q(name__icontains=q)
            | models.Q(phone__icontains=q)
            | models.Q(contact_person__icontains=q)
        )
    return render(request, "supplier_list.html", {"suppliers": suppliers, "q": q})


def supplier_create(request):
    r = must_login(request)
    if r:
        return r

    if request.method == "POST":
        errors = {}

        name = clean_text(request.POST.get("name"))
        contact_person = clean_text(request.POST.get("contact_person"))

        if not name:
            errors["name"] = "Name is required."

        try:
            phone = validate_ug_phone(request.POST.get("phone"))
        except ValidationError as e:
            errors["phone"] = str(e)
            phone = None

        if errors:
            messages.error(request, "Please correct the errors below.")
            return render(
                request,
                "supplier_form.html",
                {
                    "mode": "create",
                    "errors": errors,
                    "form_data": request.POST,
                },
            )

        Supplier.objects.create(name=name, phone=phone, contact_person=contact_person)
        messages.success(request, "Supplier added.")
        return redirect("supplier_list")

    return render(request, "supplier_form.html", {"mode": "create"})


def supplier_edit(request, pk):
    r = must_login(request)
    if r:
        return r

    supplier = get_object_or_404(Supplier, pk=pk)

    if request.method == "POST":
        errors = {}

        name = clean_text(request.POST.get("name"))
        contact_person = clean_text(request.POST.get("contact_person"))

        if not name:
            errors["name"] = "Name is required."

        try:
            phone = validate_ug_phone(request.POST.get("phone"))
        except ValidationError as e:
            errors["phone"] = str(e)
            phone = None

        if errors:
            messages.error(request, "Please correct the errors below.")
            return render(
                request,
                "supplier_form.html",
                {
                    "mode": "edit",
                    "supplier": supplier,
                    "errors": errors,
                    "form_data": request.POST,
                },
            )

        supplier.name = name
        supplier.phone = phone
        supplier.contact_person = contact_person
        supplier.save(update_fields=["name", "phone", "contact_person"])

        messages.success(request, "Supplier updated.")
        return redirect("supplier_detail", pk=supplier.pk)

    return render(request, "supplier_form.html", {"mode": "edit", "supplier": supplier})


def supplier_detail(request, pk):
    r = must_login(request)
    if r:
        return r

    supplier = get_object_or_404(Supplier, pk=pk)

    entries = (
        StockEntry.objects.select_related("product")
        .filter(supplier=supplier)
        .order_by("-created_at")
    )

    summary = entries.aggregate(
        total_supplied=Sum(F("quantity") * F("unit_cost"), output_field=DecimalField()),
        total_balance_due=Sum("balance_due"),
    )

    total_supplied = summary["total_supplied"] or Decimal("0.00")
    total_balance_due = summary["total_balance_due"] or Decimal("0.00")

    return render(
        request,
        "supplier_detail.html",
        {
            "supplier": supplier,
            "entries": entries[:50],
            "total_supplied": total_supplied,
            "total_balance_due": total_balance_due,
        },
    )


def supplier_credit_report(request):
    r = must_login(request)
    if r:
        return r

    suppliers = (
        Supplier.objects.annotate(
            outstanding=Sum(
                "stockentry__balance_due", filter=Q(stockentry__is_credit=True)
            )
        )
        .filter(outstanding__gt=0)
        .order_by("-outstanding", "name")
    )
    return render(request, "supplier_credit_report.html", {"suppliers": suppliers})
