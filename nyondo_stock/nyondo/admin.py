from django.contrib import admin

# Register your models here.
from .models import Category, Product, Supplier, StockEntry, Sale, SaleItem

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Supplier)
admin.site.register(StockEntry)
admin.site.register(Sale)
admin.site.register(SaleItem)