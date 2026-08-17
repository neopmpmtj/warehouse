from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from logging_utils import get_logger

from .services import get_catalog_updated_at, get_products

logger = get_logger("centcompras.products")


def product_list(request):
    if not request.user.is_authenticated:
        logger.warning("Unauthenticated catalogue API request from %s", request.META.get("REMOTE_ADDR"))
        return JsonResponse({"error": "Authentication required"}, status=401)

    products = list(get_products())
    logger.info(
        "Catalogue API: user=%s branch=%s products=%s",
        request.user.email,
        getattr(request, "active_branch", None),
        len(products),
    )

    data = []

    for product in products:
        data.append({
            "id": product.id,
            "description": product.description,
            "stock": str(product.stock),
            "price": str(product.price),
        })

    catalog_updated_at = get_catalog_updated_at()
    response_payload = {
        "products": data,
        "catalog_updated_at": (
            catalog_updated_at.isoformat() if catalog_updated_at else None
        ),
    }

    return JsonResponse(response_payload)


@login_required
def product_page(request):
    return render(request, "products/product_list.html")


def service_worker(request):
    return render(
        request,
        "products/service_worker.js",
        content_type="application/javascript",
    )
