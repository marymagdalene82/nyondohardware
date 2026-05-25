from django.contrib.auth import logout as auth_logout
from django.shortcuts import get_object_or_404, redirect, render
from .models import Product, Category, StockEntry, Supplier, Sale, SaleItem,DepositCustomer, DepositTransaction, DepositPickup, DepositPickupItem
from django.contrib import messages
from decimal import Decimal
from django.db import transaction, models
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from django.db.models import Sum, Count, Q, F, DecimalField, ExpressionWrapper
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.models import Group, User


# Create your views here.
# Auth landing page
def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""

        user = authenticate(request, username=username, password=password)
        if user is None:
            return render(request, "login.html", {"error": "Invalid username or password."})

        login(request, user)

        # Role-based redirect (optional)
        if user.groups.filter(name="STORE_MANAGER").exists():
            return redirect("product_list")
        if user.groups.filter(name="SALES_ATTENDANT").exists():
            return redirect("sale_list")
        if user.groups.filter(name="ACCOUNTS_ADMIN").exists():
            return redirect("dashboard")

        # default fallback
        return redirect("dashboard")

    return render(request, "login.html")

# View to handle log out
def logout_view(request):
    logout(request)
    return redirect("login")

@login_required
def user_list(request):
    require_any_group(request.user, "ACCOUNTS_ADMIN")

    q = (request.GET.get("q") or "").strip()
    users = User.objects.all().order_by("username")

    if q:
        users = users.filter(
            models.Q(username__icontains=q) |
            models.Q(first_name__icontains=q) |
            models.Q(last_name__icontains=q)
        )

    return render(request, "user_list.html", {"users": users, "q": q})

@login_required
def user_create(request):
    require_any_group(request.user, "ACCOUNTS_ADMIN")

    role_choices = ["SALES_ATTENDANT", "STORE_MANAGER", "ACCOUNTS_ADMIN"]

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        first_name = (request.POST.get("first_name") or "").strip()
        last_name = (request.POST.get("last_name") or "").strip()
        password1 = request.POST.get("password1") or ""
        password2 = request.POST.get("password2") or ""
        role = (request.POST.get("role") or "").strip()

        errors = {}

        if not username:
            errors["username"] = "Username is required."
        if not first_name:
            errors["first_name"] = "First name is required."
        if not last_name:
            errors["last_name"] = "Last name is required."
        if role not in role_choices:
            errors["role"] = "Select a valid role."

        if not password1:
            errors["password1"] = "Password is required."
        if password1 and len(password1) < 6:
            errors["password1"] = "Password must be at least 6 characters."
        if password1 != password2:
            errors["password2"] = "Passwords do not match."

        if username and User.objects.filter(username=username).exists():
            errors["username"] = "That username is already taken."

        # optional: use Django's validators (stronger)
        if password1 and not errors.get("password1"):
            try:
                validate_password(password1)
            except ValidationError as e:
                errors["password1"] = " ".join(e.messages)

        if errors:
            messages.error(request, "Please correct the errors below.")
            return render(
                request,
                "user_create.html",
                {
                    "errors": errors,
                    "form_data": request.POST,
                    "role_choices": role_choices,
                },
            )

        # Ensure group exists
        group, _ = Group.objects.get_or_create(name=role)

        user = User.objects.create_user(
            username=username,
            password=password1,
            first_name=first_name,
            last_name=last_name,
            is_staff=True,   # allows admin-like access if you later choose
            is_active=True,
        )

        # Assign exactly one role group (remove any existing)
        user.groups.clear()
        user.groups.add(group)

        messages.success(request, f"User '{username}' created and assigned role {role}.")
        return redirect("user_list")

    return render(request, "user_create.html", {"role_choices": role_choices})
# decorator to restrict access to users in a specific group (or superusers)
def require_any_group(user, *group_names):
    if user.is_superuser:
        return
    if not user.groups.filter(name__in=group_names).exists():
        raise PermissionDenied

# View to display the form and products
@login_required
def product_list(request):
    require_any_group(request.user, "SALES_ATTENDANT", "STORE_MANAGER", "ACCOUNTS_ADMIN")
    products = Product.objects.select_related("category").all()
    totals = products.aggregate(
        total_products=Count("id"),
        total_quantity=Sum("stock"),
        stock_value=Sum(F("stock") * F("unit_cost"), output_field=DecimalField()),
        low_stock_items=Count("id", filter=Q(stock__gt=0, stock__lt=F("reorder_level"))),
        out_of_stock_items=Count("id", filter=Q(stock__lte=0)),
    )

    # fallback zeros (None -> 0)
    for k in list(totals.keys()):
        totals[k] = totals[k] or 0
    return render(request, "list.html", {"products": products, "totals": totals})


# View to handle product creation
@login_required
def product_create(request):
    require_any_group(request.user, "STORE_MANAGER")
    if request.method == "POST":
        product_name = request.POST.get("product_name", "").strip()
        category_id = request.POST.get("category")
        variant = request.POST.get("variant") or None
        unit = request.POST.get("unit", "").strip()

        try:
            unit_cost = Decimal(request.POST.get("unit_cost") or "0")
            unit_price = Decimal(request.POST.get("unit_price") or "0")
        except:
            messages.error(request, "Invalid price values.")
            return redirect("add_product")

        reorder_level = int(request.POST.get("reorder_level") or 0)

        if not product_name:
            messages.error(request, "Product name is required.")
        elif not category_id:
            messages.error(request, "Category is required.")
        elif not unit:
            messages.error(request, "Unit is required.")
        elif unit_price <= unit_cost:
            messages.error(request, "Selling price must be greater than cost price.")
        else:
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
            return redirect("product_list")

    categories = Category.objects.all().order_by("name")
    return render(request, "add_product.html", {"categories": categories})


# View to add stock when suppliers deliver products
@login_required
def add_stock(request):
    require_any_group(request.user, "STORE_MANAGER")
    products = Product.objects.all()
    suppliers = Supplier.objects.all()
    if request.method == "POST":
        product_id = request.POST.get("product")
        supplier_id = request.POST.get("supplier")
        quantity = Decimal(request.POST.get("quantity") or "0")
        unit_cost = Decimal(request.POST.get("unit_cost") or "0")
        unit_price = Decimal(request.POST.get("unit_price") or "0")
        is_credit = request.POST.get("is_credit") == "True"
        amount_paid = Decimal(request.POST.get("amount_paid") or 0)

        StockEntry.objects.create(
            product_id=product_id,
            supplier_id=supplier_id,
            quantity=quantity,
            unit_cost=unit_cost,
            unit_price=unit_price,
            is_credit=is_credit,
            amount_paid=amount_paid,
        )
        return redirect("stock_entry_list")
    context = {
        "products": products,
        "suppliers": suppliers,
    }

    return render(request, "stock_entry_form.html", context)

@login_required

def stock_entry_list(request):
    require_any_group(request.user, "SALES_ATTENDANT", "STORE_MANAGER", "ACCOUNTS_ADMIN")
    entries = StockEntry.objects.select_related("product", "supplier").order_by(
        "-created_at"
    )
    credit_only = request.GET.get("credit_only") == "1"
    if credit_only:
        # show only credit entries that still have a balance due
        entries = entries.filter(is_credit=True, balance_due__gt=0)
    totals = entries.aggregate(
    entries_count=Count("id"),
    total_quantity=Sum("quantity"),
    total_value=Sum(F("quantity") * F("unit_cost"), output_field=DecimalField()),
    total_paid=Sum("amount_paid"),
    total_balance=Sum("balance_due"),
)
    for k in list(totals.keys()):
        totals[k] = totals[k] or 0

    return render(
        request,
        "stock_entry_list.html",
        {"entries": entries, "credit_only": credit_only, "totals": totals},
    )


# View to edit product details
@login_required
def product_edit(request, pk):
    require_any_group(request.user, "STORE_MANAGER")
    product = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        product_name = request.POST.get("product_name", "").strip()
        category_id = request.POST.get("category")
        variant = request.POST.get("variant") or None
        unit = request.POST.get("unit", "").strip()

        try:
            unit_cost = Decimal(request.POST.get("unit_cost") or "0")
            unit_price = Decimal(request.POST.get("unit_price") or "0")
        except:
            messages.error(request, "Invalid price values.")
            return redirect("product_edit", pk=pk)

        reorder_level = int(request.POST.get("reorder_level") or 0)

        if not product_name:
            messages.error(request, "Product name is required.")
        elif not category_id:
            messages.error(request, "Category is required.")
        elif not unit:
            messages.error(request, "Unit is required.")
        elif unit_price <= unit_cost:
            messages.error(request, "Selling price must be greater than cost price.")
        else:
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

    categories = Category.objects.all().order_by("name")
    return render(
        request, "product_edit.html", {"product": product, "categories": categories}
    )


# View to delete a product
@login_required
def product_delete(request, pk):
    require_any_group(request.user, "STORE_MANAGER")
    product = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        product.delete()
        messages.success(request, "Product deleted.")
        return redirect("product_list")

    return render(request, "product_confirm_delete.html", {"product": product})


# View to display product details
from django.shortcuts import get_object_or_404


@login_required
def product_detail(request, pk):
    require_any_group(request.user, "SALES_ATTENDANT", "STORE_MANAGER", "ACCOUNTS_ADMIN")
  
    product = get_object_or_404(Product.objects.select_related("category"), pk=pk)

    # optional: show recent stock arrivals for this product
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


# View to display stock entry details
@login_required
def stock_entry_detail(request, pk):
    require_any_group(request.user, "SALES_ATTENDANT", "STORE_MANAGER", "ACCOUNTS_ADMIN")
    entry = get_object_or_404(
        StockEntry.objects.select_related("product", "supplier"), pk=pk
    )
    return render(request, "stock_entry_detail.html", {"entry": entry})


# View to handle payments for credit stock entries
@login_required
def stock_entry_pay(request, pk):
    require_any_group(request.user, "STORE_MANAGER")
    entry = get_object_or_404(
        StockEntry.objects.select_related("product", "supplier"), pk=pk
    )

    if request.method == "POST":
        try:
            pay_amount = Decimal(request.POST.get("pay_amount") or "0")
        except:
            messages.error(request, "Enter a valid payment amount.")
            return redirect("stock_entry_pay", pk=pk)

        if pay_amount <= 0:
            messages.error(request, "Payment must be greater than 0.")
            return redirect("stock_entry_pay", pk=pk)

        if entry.balance_due <= 0:
            messages.info(request, "This entry has no balance due.")
            return redirect("stock_entry_list")

        # clamp payment so it can't exceed balance
        if pay_amount > entry.balance_due:
            pay_amount = entry.balance_due

        with transaction.atomic():
            # update fields directly (no StockEntry.save call)
            StockEntry.objects.filter(pk=entry.pk).update(
                amount_paid=entry.amount_paid + pay_amount,
                balance_due=entry.balance_due - pay_amount,
                is_credit=(entry.balance_due - pay_amount) > 0,
            )

        messages.success(request, "Payment recorded.")
        return redirect("stock_entry_list")

    return render(request, "stock_entry_pay.html", {"entry": entry})


# Views for sales management
@login_required
def sale_list(request):
    require_any_group(request.user, "SALES_ATTENDANT", "STORE_MANAGER", "ACCOUNTS_ADMIN")
    sales = Sale.objects.prefetch_related("items").all().order_by("-sale_date")
    totals = sales.aggregate(
    sales_count=Count("id"),
    total_revenue=Sum("total_amount"),
    transport_total=Sum("transport_charge"),
)
    for k in list(totals.keys()):
        totals[k] = totals[k] or 0
    context = {"sales": sales, "totals": totals}
    return render(request, "sale_list.html", context)


@login_required
def sale_detail(request, pk):
    require_any_group(request.user, "SALES_ATTENDANT", "STORE_MANAGER", "ACCOUNTS_ADMIN")
    sale = get_object_or_404(Sale.objects.prefetch_related("items__product"), pk=pk)
    return render(request, "sale_detail.html", {"sale": sale})


@login_required
def sale_create(request):
    require_any_group(request.user, "SALES_ATTENDANT", "STORE_MANAGER", "ACCOUNTS_ADMIN")
    if request.method == "POST":
        customer_name = (request.POST.get("customer_name") or "").strip()
        customer_type = request.POST.get("customer_type")
        distance_km = Decimal(request.POST.get("distance_km") or "0")

        products = request.POST.getlist("product[]")
        quantities = request.POST.getlist("quantity[]")

        # Basic validation
        if not customer_type:
            messages.error(request, "Customer type is required.")
            return redirect("sale_create")

        if not products or not quantities or len(products) != len(quantities):
            messages.error(request, "Please add at least one product with quantity.")
            return redirect("sale_create")

        with transaction.atomic():
            sale = Sale.objects.create(
                customer_name=customer_name,
                customer_type=customer_type,
                distance_km=float(distance_km),
                total_amount=Decimal("0.00"),
                transport_charge=Decimal("0.00"),
                processed_by=request.user,
            )

            items_total = Decimal("0.00")

            for product_id, qty in zip(products, quantities):
                if not product_id:
                    continue

                try:
                    quantity = int(qty)
                except:
                    raise ValidationError("Quantity must be a whole number.")

                if quantity <= 0:
                    raise ValidationError("Quantity must be greater than 0.")

                product = get_object_or_404(Product, pk=product_id)

                # stock check
                if product.stock < quantity:
                    raise ValidationError(
                        f"Not enough stock for {product.product_name}. Available: {product.stock}"
                    )

                unit_price = product.unit_price
                subtotal = Decimal(quantity) * unit_price

                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=quantity,
                    # unit_price=unit_price,
                    # subtotal=subtotal,
                )

                # reduce stock (do it here or rely on SaleItem.save; choose ONE)
                # Product.objects.filter(pk=product.pk).update(
                #     stock=product.stock - quantity
                # )

                items_total += subtotal

            # compute transport based on items_total
            sale.total_amount = items_total
            sale.transport_charge = sale.calculate_transport()
            sale.total_amount = sale.total_amount + sale.transport_charge
            sale.save(update_fields=["total_amount", "transport_charge"])

        messages.success(request, "Sale created successfully!")
        return redirect("sale_detail", pk=sale.pk)

    products = Product.objects.all().order_by("product_name")
    return render(request, "create_sale.html", {"products": products})

@login_required
def sale_receipt(request, pk):
    require_any_group(request.user, "SALES_ATTENDANT", "STORE_MANAGER", "ACCOUNTS_ADMIN")
    sale = get_object_or_404(Sale.objects.prefetch_related("items__product"), pk=pk)
    return render(request, "receipt.html", {"sale": sale})

# Views for deposit management
@login_required
def deposit_customer_list(request):
    require_any_group(request.user, "ACCOUNTS_ADMIN")
    q = (request.GET.get("q") or "").strip()
    customers = DepositCustomer.objects.all().order_by("-id")
    if q:
        customers = customers.filter(
            models.Q(full_name__icontains=q) |
            models.Q(nin__icontains=q) |
            models.Q(phone__icontains=q)
        )
    return render(request, "deposit_customer_list.html", {"customers": customers, "q": q})

@login_required
def deposit_customer_create(request):
    require_any_group(request.user, "ACCOUNTS_ADMIN")
    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        nin = (request.POST.get("nin") or "").strip().upper()
        phone = (request.POST.get("phone") or "").strip()
        address = (request.POST.get("address") or "").strip()
        occupation = (request.POST.get("occupation") or "").strip()

        if not full_name or not nin or not phone:
            messages.error(request, "Full name, NIN and phone are required.")
            return redirect("deposit_customer_create")

        try:
            customer = DepositCustomer.objects.create(
                full_name=full_name,
                nin=nin,
                phone=phone,
                address=address,
                occupation=occupation,
            )
            messages.success(request, "Deposit customer registered.")
            return redirect("deposit_customer_detail", pk=customer.pk)
        except Exception as e:
            messages.error(request, f"Could not register customer: {e}")
            return redirect("deposit_customer_create")

    return render(request, "deposit_customer_form.html")

@login_required
def deposit_customer_detail(request, pk):
    require_any_group(request.user, "ACCOUNTS_ADMIN")
    customer = get_object_or_404(DepositCustomer, pk=pk)
    transactions = customer.transactions.order_by("-created_at")[:20]
    pickups = customer.pickups.order_by("-created_at")[:10]
    return render(
        request,
        "deposit_customer_detail.html",
        {"customer": customer, "transactions": transactions, "pickups": pickups},
    )

@login_required
def deposit_make(request, pk):
    require_any_group(request.user, "ACCOUNTS_ADMIN")
    customer = get_object_or_404(DepositCustomer, pk=pk)

    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount") or "0")
        except:
            messages.error(request, "Enter a valid amount.")
            return redirect("deposit_make", pk=pk)

        notes = (request.POST.get("notes") or "").strip()

        if amount <= 0:
            messages.error(request, "Deposit amount must be greater than 0.")
            return redirect("deposit_make", pk=pk)

        tx = DepositTransaction.objects.create(
            customer=customer,
            tx_type="DEPOSIT",
            amount=amount,
            notes=notes,
        )

        messages.success(request, "Deposit recorded.")
        return redirect("deposit_receipt", pk=tx.pk)

    return render(request, "deposit_make.html", {"customer": customer})

@login_required
def deposit_receipt(request, pk):
    require_any_group(request.user, "ACCOUNTS_ADMIN")
    tx = get_object_or_404(
        DepositTransaction.objects.select_related("customer"),
        pk=pk,
        tx_type="DEPOSIT",
    )
    return render(request, "deposit_receipt.html", {"tx": tx})


@login_required
def deposit_pickup_create(request, pk):
    require_any_group(request.user, "ACCOUNTS_ADMIN")
    customer = get_object_or_404(DepositCustomer, pk=pk)
    eligible_products = Product.objects.select_related("category").filter(
        category__is_deposit_allowed=True
    ).order_by("product_name")

    if request.method == "POST":
        product_id = request.POST.get("product")
        qty_raw = request.POST.get("quantity") or "0"

        if not product_id:
            messages.error(request, "Select a product.")
            return redirect("deposit_pickup_create", pk=pk)

        try:
            quantity = int(qty_raw)
        except:
            messages.error(request, "Enter a valid quantity.")
            return redirect("deposit_pickup_create", pk=pk)

        if quantity <= 0:
            messages.error(request, "Quantity must be greater than 0.")
            return redirect("deposit_pickup_create", pk=pk)

        product = get_object_or_404(Product.objects.select_related("category"), pk=product_id)

        if not product.category.is_deposit_allowed:
            messages.error(request, "This product is not eligible for deposit scheme.")
            return redirect("deposit_pickup_create", pk=pk)

        if product.stock < quantity:
            messages.error(request, f"Not enough stock. Available: {product.stock}")
            return redirect("deposit_pickup_create", pk=pk)

        unit_price = product.unit_price  # rule #2: current price
        total_cost = Decimal(quantity) * unit_price

        if customer.balance < total_cost:
            messages.error(
                request,
                f"Insufficient deposit balance. Balance: UGX {customer.balance}. Required: UGX {total_cost}."
            )
            return redirect("deposit_pickup_create", pk=pk)

        with transaction.atomic():
            pickup = DepositPickup.objects.create(customer=customer)
            item = DepositPickupItem.objects.create(
                pickup=pickup,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
            )

            # reduce stock
            Product.objects.filter(pk=product.pk).update(stock=product.stock - quantity)

            # ledger deduction (always positive amount)
            DepositTransaction.objects.create(
                customer=customer,
                tx_type="PICKUP",
                amount=total_cost,
                notes=f"Pickup #{pickup.pk}",
                related_pickup=pickup,
            )

        messages.success(request, "Pickup recorded.")
        return redirect("deposit_pickup_receipt", pk=pickup.pk)

    return render(
        request,
        "deposit_pickup_form.html",
        {"customer": customer, "products": eligible_products},
    )


@login_required
def deposit_pickup_receipt(request, pk):
    require_any_group(request.user, "ACCOUNTS_ADMIN")
    pickup = get_object_or_404(
        DepositPickup.objects.select_related("customer").prefetch_related("items__product"),
        pk=pk
    )
    return render(request, "deposit_pickup_receipt.html", {"pickup": pickup})

# Views for supplier management
@login_required
def supplier_list(request):
    require_any_group(request.user, "STORE_MANAGER", "ACCOUNTS_ADMIN")
    q = (request.GET.get("q") or "").strip()
    suppliers = Supplier.objects.all().order_by("name")
    if q:
        suppliers = suppliers.filter(
            models.Q(name__icontains=q) |
            models.Q(phone__icontains=q) |
            models.Q(contact_person__icontains=q)
        )
    return render(request, "supplier_list.html", {"suppliers": suppliers, "q": q})


@login_required
def supplier_create(request):
    require_any_group(request.user, "STORE_MANAGER", "ACCOUNTS_ADMIN")
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        contact_person = (request.POST.get("contact_person") or "").strip()

        if not name or not phone:
            messages.error(request, "Name and phone are required.")
            return redirect("supplier_create")

        Supplier.objects.create(name=name, phone=phone, contact_person=contact_person)
        messages.success(request, "Supplier added.")
        return redirect("supplier_list")

    return render(request, "supplier_form.html", {"mode": "create"})


@login_required
def supplier_edit(request, pk):
    require_any_group(request.user, "STORE_MANAGER", "ACCOUNTS_ADMIN")
    supplier = get_object_or_404(Supplier, pk=pk)

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        contact_person = (request.POST.get("contact_person") or "").strip()

        if not name or not phone:
            messages.error(request, "Name and phone are required.")
            return redirect("supplier_edit", pk=pk)

        supplier.name = name
        supplier.phone = phone
        supplier.contact_person = contact_person
        supplier.save(update_fields=["name", "phone", "contact_person"])

        messages.success(request, "Supplier updated.")
        return redirect("supplier_detail", pk=supplier.pk)

    return render(request, "supplier_form.html", {"mode": "edit", "supplier": supplier})


@login_required
def supplier_detail(request, pk):
    require_any_group(request.user, "STORE_MANAGER", "ACCOUNTS_ADMIN")
    supplier = get_object_or_404(Supplier, pk=pk)

    entries = (
        StockEntry.objects.select_related("product")
        .filter(supplier=supplier)
        .order_by("-created_at")
    )

    summary = entries.aggregate(
        total_supplied=models.Sum(models.F("quantity") * models.F("unit_cost")),
        total_balance_due=models.Sum("balance_due"),
    )

    # fallback zeros
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


@login_required
def supplier_credit_report(request):
    require_any_group(request.user,"ACCOUNTS_ADMIN")
    suppliers = (
        Supplier.objects.annotate(
            outstanding=Sum(
                "stockentry__balance_due",
                filter=Q(stockentry__is_credit=True),
            )
        )
        .filter(outstanding__gt=0)
        .order_by("-outstanding", "name")
    )
    return render(request, "supplier_credit_report.html", {"suppliers": suppliers})

# Views for reporting
@login_required
def dashboard(request):
    require_any_group(request.user, "ACCOUNTS_ADMIN")
    today = timezone.localdate()

    sales_today = Sale.objects.filter(sale_date__date=today)

    sales_today_summary = sales_today.aggregate(
        count=Count("id"),
        total=Sum("total_amount"),
        transport=Sum("transport_charge"),
    )

    items_today = SaleItem.objects.filter(sale__sale_date__date=today).aggregate(
        qty=Sum("quantity")
    )

    low_stock = Product.objects.filter(stock__gt=0, stock__lt=F("reorder_level")).order_by("stock")[:10]
    out_of_stock = Product.objects.filter(stock__lte=0).order_by("product_name")[:10]

    supplier_credit_total = StockEntry.objects.filter(is_credit=True).aggregate(
        total=Sum("balance_due")
    )["total"] or Decimal("0.00")

    top_credit_suppliers = (
        Supplier.objects.annotate(
            outstanding=Sum(
                "stockentry__balance_due",
                filter=Q(stockentry__is_credit=True),
            )
        )
        .filter(outstanding__gt=0)
        .order_by("-outstanding")[:5]
    )

    # deposit scheme totals (balance is computed per customer; easiest is sum in python)
    deposit_customers = DepositCustomer.objects.all()
    total_deposit_balance = sum((c.balance for c in deposit_customers), Decimal("0.00"))

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
        "items_today_qty": items_today["qty"] or 0,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
        "supplier_credit_total": supplier_credit_total,
        "top_credit_suppliers": top_credit_suppliers,
        "total_deposit_balance": total_deposit_balance,
        "deposit_today": deposit_today,
        "pickup_today": pickup_today,
    }
    return render(request, "dashboard.html", context)

@login_required
def report_sales_summary(request):
    require_any_group(request.user, "ACCOUNTS_ADMIN")
    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""
    customer_type = request.GET.get("customer_type") or ""

    qs = Sale.objects.all().order_by("-sale_date")

    if date_from:
        qs = qs.filter(sale_date__date__gte=date_from)
    if date_to:
        qs = qs.filter(sale_date__date__lte=date_to)
    if customer_type:
        qs = qs.filter(customer_type=customer_type)

    summary = qs.aggregate(
        count=Count("id"),
        total=Sum("total_amount"),
        transport=Sum("transport_charge"),
    )

    return render(
        request,
        "report_sales_summary.html",
        {
            "sales": qs[:200],
            "summary": summary,
            "date_from": date_from,
            "date_to": date_to,
            "customer_type": customer_type,
            "customer_types": Sale.CUSTOMER_TYPE,
        },
    )

@login_required
def report_product_sales(request):
    require_any_group(request.user, "ACCOUNTS_ADMIN")
    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""

    items = SaleItem.objects.select_related("product", "sale")

    if date_from:
        items = items.filter(sale__sale_date__date__gte=date_from)
    if date_to:
        items = items.filter(sale__sale_date__date__lte=date_to)

    revenue_expr = ExpressionWrapper(F("quantity") * F("unit_price"), output_field=DecimalField())

    rows = (
        items.values("product__id", "product__product_name")
        .annotate(
            qty=Sum("quantity"),
            revenue=Sum(revenue_expr),
        )
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

@login_required
def report_stock_levels(request):
    require_any_group(request.user, "ACCOUNTS_ADMIN")
    low_only = request.GET.get("low_only") == "1"
    qs = Product.objects.select_related("category").all().order_by("product_name")

    if low_only:
        qs = qs.filter(stock__lt=F("reorder_level"))

    return render(request, "report_stock_levels.html", {"products": qs, "low_only": low_only})

@login_required
def report_deposit_summary(request):
    require_any_group(request.user, "ACCOUNTS_ADMIN")
    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""

    txs = DepositTransaction.objects.select_related("customer").all().order_by("-created_at")

    if date_from:
        txs = txs.filter(created_at__date__gte=date_from)
    if date_to:
        txs = txs.filter(created_at__date__lte=date_to)

    deposits_total = txs.filter(tx_type="DEPOSIT").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    pickups_total = txs.filter(tx_type="PICKUP").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

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