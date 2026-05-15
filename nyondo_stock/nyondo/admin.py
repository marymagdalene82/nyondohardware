from django.contrib import admin

# Register your models here.
from .models import Category, Product, Supplier, StockEntry, Sale, SaleItem,DepositCustomer, DepositTransaction, DepositPickup, DepositPickupItem

admin.site.register(DepositCustomer)
admin.site.register(DepositTransaction)
admin.site.register(DepositPickup)
admin.site.register(DepositPickupItem)

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Supplier)
admin.site.register(StockEntry)
admin.site.register(Sale)
admin.site.register(SaleItem)