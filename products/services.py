from decimal import Decimal

from django.db import transaction

from logging_utils import get_logger

from .models import Product, ProductChangeLog

logger = get_logger("centcompras.products")

UPDATABLE_FIELDS = ("internal_code", "description", "stock", "price")


def _serialize_value(value):
    if isinstance(value, Decimal):
        return str(value)
    return value


def _log_change(product, user, action, changes):
    ProductChangeLog.objects.create(
        product=product,
        user=user,
        action=action,
        changes=changes,
    )


@transaction.atomic
def create_product(user, description, stock, price, internal_code=""):
    product = Product.objects.create(
        internal_code=internal_code.strip(),
        description=description,
        stock=Decimal(str(stock)),
        price=Decimal(str(price)),
        is_active=True,
    )

    _log_change(
        product,
        user,
        ProductChangeLog.Action.CREATED,
        {
            "internal_code": _serialize_value(product.internal_code),
            "description": product.description,
            "stock": _serialize_value(product.stock),
            "price": _serialize_value(product.price),
        },
    )

    logger.info(
        "Created product id=%s internal_code=%r description=%r stock=%s price=%s user=%s",
        product.id,
        product.internal_code,
        product.description,
        product.stock,
        product.price,
        getattr(user, "email", None),
    )

    return product


@transaction.atomic
def update_product(user, product, **fields):
    if not fields:
        return product

    unknown = set(fields) - set(UPDATABLE_FIELDS)
    if unknown:
        raise ValueError(f"Cannot update fields: {', '.join(sorted(unknown))}")

    # Reload from DB — callers (e.g. Django admin) may pass an in-memory instance
    # already mutated by form.save(commit=False), which would hide real diffs.
    product = Product.objects.select_for_update().get(pk=product.pk)

    changes = {}

    for field_name, new_value in fields.items():
        if field_name in ("stock", "price"):
            new_value = Decimal(str(new_value))
        elif field_name == "internal_code":
            new_value = new_value.strip()

        old_value = getattr(product, field_name)
        if old_value != new_value:
            changes[field_name] = {
                "old": _serialize_value(old_value),
                "new": _serialize_value(new_value),
            }
            setattr(product, field_name, new_value)

    if not changes:
        return product

    product.save(update_fields=[*changes.keys(), "updated_at"])
    _log_change(product, user, ProductChangeLog.Action.UPDATED, changes)

    logger.info(
        "Updated product id=%s changes=%s user=%s",
        product.id,
        list(changes.keys()),
        getattr(user, "email", None),
    )

    return product


@transaction.atomic
def deactivate_product(user, product):
    if not product.is_active:
        return product

    product.is_active = False
    product.save(update_fields=["is_active", "updated_at"])
    _log_change(product, user, ProductChangeLog.Action.DEACTIVATED, {})

    logger.info(
        "Deactivated product id=%s user=%s",
        product.id,
        getattr(user, "email", None),
    )

    return product


@transaction.atomic
def reactivate_product(user, product):
    if product.is_active:
        return product

    product.is_active = True
    product.save(update_fields=["is_active", "updated_at"])
    _log_change(product, user, ProductChangeLog.Action.REACTIVATED, {})

    logger.info(
        "Reactivated product id=%s user=%s",
        product.id,
        getattr(user, "email", None),
    )

    return product


def get_products(active_only=True):
    queryset = Product.objects.all().order_by("id")
    if active_only:
        queryset = queryset.active()
    return queryset


def get_product_history(product):
    return product.change_logs.select_related("user").order_by("-created_at")
