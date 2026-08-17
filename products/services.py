from decimal import Decimal

from .models import Product


def create_product(description, stock, price):
    product = Product.objects.create(
        description=description,
        stock=Decimal(str(stock)),
        price=Decimal(str(price)),
    )

    return product


def get_products():
    return Product.objects.all().order_by("id")