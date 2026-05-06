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
    path('admin/', admin.site.urls),
    # Path for the add product view
    path('add_product/', web_views.product_create, name='add_product'),
    # Default path to display the form and products
    path('product_list/', web_views.product_list, name='product_list'),
]
