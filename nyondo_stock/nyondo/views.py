from urllib import request
from django.shortcuts import get_object_or_404, redirect, render
from .models import Product, Category, StockEntry, Supplier, Sale, SaleItem,DepositCustomer, DepositTransaction, DepositPickup, DepositPickupItem
from django.contrib import messages
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError


# Create your views here.
# View to display the form and products
def product_list(request):
    products = Product.objects.select_related("category").all()
    return render(request, "list.html", {"products": products})


# View to handle product creation
def product_create(request):
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
def add_stock(request):
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


def stock_entry_list(request):

    entries = StockEntry.objects.select_related("product", "supplier").order_by(
        "-created_at"
    )
    credit_only = request.GET.get("credit_only") == "1"
    if credit_only:
        entries = entries.filter(is_credit=True)

    return render(
        request,
        "stock_entry_list.html",
        {"entries": entries, "credit_only": credit_only},
    )


# View to edit product details
def product_edit(request, pk):
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
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        product.delete()
        messages.success(request, "Product deleted.")
        return redirect("product_list")

    return render(request, "product_confirm_delete.html", {"product": product})


# View to display product details
from django.shortcuts import get_object_or_404


def product_detail(request, pk):
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
def stock_entry_detail(request, pk):
    entry = get_object_or_404(
        StockEntry.objects.select_related("product", "supplier"), pk=pk
    )
    return render(request, "stock_entry_detail.html", {"entry": entry})


# View to handle payments for credit stock entries
def stock_entry_pay(request, pk):
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
def sale_list(request):
    sales = Sale.objects.prefetch_related("items").all().order_by("-sale_date")
    context = {"sales": sales}
    return render(request, "sale_list.html", context)


def sale_detail(request, pk):
    sale = get_object_or_404(Sale.objects.prefetch_related("items__product"), pk=pk)
    return render(request, "sale_detail.html", {"sale": sale})


def sale_create(request):
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
                    unit_price=unit_price,
                    subtotal=subtotal,
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


def sale_receipt(request, pk):
    sale = get_object_or_404(Sale.objects.prefetch_related("items__product"), pk=pk)
    return render(request, "receipt.html", {"sale": sale})
