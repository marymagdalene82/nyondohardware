from django.contrib import admin

# Register your models here.
from .models import Category, Product, Supplier, StockEntry

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Supplier)
admin.site.register(StockEntry)