from django.shortcuts import redirect, render
from .models import Product
from django.contrib import messages

# Create your views here.
# View to display the form and products
def product_list(request):
    products = Product.objects.all()
    context = {'products': products
    }
    return render(request, 'list.html', context)
# View to handle product creation 
def product_create(request):
    if request.method == "POST":
        payload = request.POST
        product_name = payload.get('product_name')
        category = payload.get('category')
        variant = payload.get('variant')
        unit = payload.get('unit')
        
        unit_cost = payload.get('unit_cost')
        unit_price = payload.get('unit_price')
        reorder_level = payload.get('reorder_level')

        new_product = Product()
        new_product.product_name = product_name
        new_product.category = category
        new_product.variant = variant
        new_product.unit = unit
        
        new_product.unit_cost = unit_cost
        new_product.unit_price = unit_price
        new_product.reorder_level = reorder_level
        new_product.save()
        messages.success(request, "Product added successfully!")
        return redirect("product_list")
    return render(request, 'add_product.html')
    
    
    


    
