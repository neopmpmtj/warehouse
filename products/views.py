from django.http import JsonResponse

from .services import get_products

from django.shortcuts import render


def product_list(request):
    products = get_products()

    data = []

    for product in products:
        data.append({
            "id": product.id,
            "description": product.description,
            "stock": str(product.stock),
            "price": str(product.price),
        })

    return JsonResponse({"products": data})

def product_page(request):
    return render(request, "products/product_list.html")

def service_worker(request):
    return render(
        request,
        "products/service_worker.js",
        content_type="application/javascript",
    )