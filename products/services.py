from decimal import Decimal

from logging_utils import get_logger

from .models import Product

logger = get_logger("centcompras.products")


def create_product(description, stock, price):
    product = Product.objects.create(
        description=description,
        stock=Decimal(str(stock)),
        price=Decimal(str(price)),
    )

    logger.info(
        "Created product id=%s description=%r stock=%s price=%s",
        product.id,
        product.description,
        product.stock,
        product.price,
    )

    return product


def get_products():
    products = Product.objects.all().order_by("id")
    logger.debug("Fetched %s products from database", products.count())
    return products