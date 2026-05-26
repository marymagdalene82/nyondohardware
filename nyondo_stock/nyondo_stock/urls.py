"""
URL configuration for nyondo_stock project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.urls import path
from nyondo import views as web_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", web_views.dashboard, name="dashboard"),
    path("login/", web_views.login_view, name="login"),
    path("logout/", web_views.logout_view, name="logout"),
  
    # Home page
    
    # Path for the add product view
    path("add_product/", web_views.product_create, name="add_product"),
    # Default path to display the form and products
    path("product_list/", web_views.product_list, name="product_list"),
    # Path to handle adding stock when suppliers deliver products
    path("stock/add/", web_views.add_stock, name="add_stock"),
    path("products/<int:pk>/delete/", web_views.product_delete, name="product_delete"),
    path("products/<int:pk>/", web_views.product_detail, name="product_detail"),
    # Path to view stock levels and product details
    path("stock/history/", web_views.stock_entry_list, name="stock_entry_list"),
    path("products/<int:pk>/edit/", web_views.product_edit, name="product_edit"),
    path("stock/<int:pk>/", web_views.stock_entry_detail, name="stock_entry_detail"),
    path("stock/<int:pk>/pay/", web_views.stock_entry_pay, name="stock_entry_pay"),
    # Paths for sales
    path("sales/", web_views.sale_list, name="sale_list"),
    path("sales/create/", web_views.sale_create, name="sale_create"),
    path("sales/<int:pk>/", web_views.sale_detail, name="sale_detail"),
    path("sales/<int:pk>/receipt/", web_views.sale_receipt, name="sale_receipt"),
    # Paths for deposits
    path(
        "deposits/customers/",
        web_views.deposit_customer_list,
        name="deposit_customer_list",
    ),
    path(
        "deposits/customers/new/",
        web_views.deposit_customer_create,
        name="deposit_customer_create",
    ),
    path(
        "deposits/customers/<int:pk>/",
        web_views.deposit_customer_detail,
        name="deposit_customer_detail",
    ),
    path(
        "deposits/customers/<int:pk>/deposit/",
        web_views.deposit_make,
        name="deposit_make",
    ),
    path(
        "deposits/transactions/<int:pk>/receipt/",
        web_views.deposit_receipt,
        name="deposit_receipt",
    ),
    path(
        "deposits/customers/<int:pk>/pickup/",
        web_views.deposit_pickup_create,
        name="deposit_pickup_create",
    ),
    path(
        "deposits/pickups/<int:pk>/receipt/",
        web_views.deposit_pickup_receipt,
        name="deposit_pickup_receipt",
    ),
    # Paths for suppliers
    path("suppliers/", web_views.supplier_list, name="supplier_list"),
    path("suppliers/new/", web_views.supplier_create, name="supplier_create"),
    path("suppliers/<int:pk>/", web_views.supplier_detail, name="supplier_detail"),
    path("suppliers/<int:pk>/edit/", web_views.supplier_edit, name="supplier_edit"),
    path(
        "suppliers/credit/",
        web_views.supplier_credit_report,
        name="supplier_credit_report",
    ),
    # Paths for reporting
    path("reports/sales/", web_views.report_sales_summary, name="report_sales_summary"),
    path(
        "reports/products/", web_views.report_product_sales, name="report_product_sales"
    ),
    path("reports/stock/", web_views.report_stock_levels, name="report_stock_levels"),
    path(
        "reports/deposits/",
        web_views.report_deposit_summary,
        name="report_deposit_summary",
    ),
]
