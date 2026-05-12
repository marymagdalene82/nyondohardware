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
from django.urls import path
from nyondo import views as web_views

urlpatterns = [
    path("admin/", admin.site.urls),
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
]
