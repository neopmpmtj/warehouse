from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max

from logging_utils import get_logger

from .models import Product, ProductChangeLog, ProductSupplier, Supplier

logger = get_logger("centcompras.products")

UPDATABLE_FIELDS = ("internal_code", "description", "stock", "price")


class DuplicateInternalCodeError(ValidationError):
    def __init__(self, internal_code):
        super().__init__(
            f'Internal code "{internal_code}" is already used by another product.',
            code="duplicate_internal_code",
        )


def _serialize_value(value):
    if isinstance(value, Decimal):
        return str(value)
    return value


def _normalize_internal_code(internal_code):
    return internal_code.strip()


def validate_internal_code_available(internal_code, exclude_product_id=None):
    internal_code = _normalize_internal_code(internal_code)
    if not internal_code:
        return

    queryset = Product.objects.filter(internal_code=internal_code)
    if exclude_product_id is not None:
        queryset = queryset.exclude(pk=exclude_product_id)

    if queryset.exists():
        raise DuplicateInternalCodeError(internal_code)


def _log_change(product, user, action, changes, reason=""):
    ProductChangeLog.objects.create(
        product=product,
        user=user,
        action=action,
        changes=changes,
        reason=reason.strip(),
    )


def _save_product(product, update_fields=None):
    try:
        if update_fields is None:
            product.save()
        else:
            product.save(update_fields=update_fields)
    except IntegrityError as exc:
        if "unique_product_internal_code_when_set" in str(exc):
            raise DuplicateInternalCodeError(product.internal_code) from exc
        raise


@transaction.atomic
def create_product(user, description, stock, price, internal_code="", reason=""):
    internal_code = _normalize_internal_code(internal_code)
    validate_internal_code_available(internal_code)

    product = Product(
        internal_code=internal_code,
        description=description,
        stock=Decimal(str(stock)),
        price=Decimal(str(price)),
        is_active=True,
    )
    _save_product(product, update_fields=None)

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
        reason=reason,
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
def update_product(user, product, reason="", **fields):
    if not fields:
        return product

    unknown = set(fields) - set(UPDATABLE_FIELDS)
    if unknown:
        raise ValueError(f"Cannot update fields: {', '.join(sorted(unknown))}")

    # Reload from DB — callers (e.g. Django admin) may pass an in-memory instance
    # already mutated by form.save(commit=False), which would hide real diffs.
    product = Product.objects.select_for_update().get(pk=product.pk)

    changes = {}
    pending_internal_code = None

    for field_name, new_value in fields.items():
        if field_name in ("stock", "price"):
            new_value = Decimal(str(new_value))
        elif field_name == "internal_code":
            new_value = _normalize_internal_code(new_value)
            pending_internal_code = new_value

        old_value = getattr(product, field_name)
        if old_value != new_value:
            changes[field_name] = {
                "old": _serialize_value(old_value),
                "new": _serialize_value(new_value),
            }
            setattr(product, field_name, new_value)

    if not changes:
        return product

    if pending_internal_code is not None:
        validate_internal_code_available(
            pending_internal_code,
            exclude_product_id=product.pk,
        )

    _save_product(product, update_fields=[*changes.keys(), "updated_at"])
    _log_change(
        product,
        user,
        ProductChangeLog.Action.UPDATED,
        changes,
        reason=reason,
    )

    logger.info(
        "Updated product id=%s changes=%s user=%s",
        product.id,
        list(changes.keys()),
        getattr(user, "email", None),
    )

    return product


@transaction.atomic
def deactivate_product(user, product, reason=""):
    product = Product.objects.select_for_update().get(pk=product.pk)
    if not product.is_active:
        return product

    product.is_active = False
    _save_product(product, update_fields=["is_active", "updated_at"])
    _log_change(
        product,
        user,
        ProductChangeLog.Action.DEACTIVATED,
        {},
        reason=reason,
    )

    logger.info(
        "Deactivated product id=%s user=%s",
        product.id,
        getattr(user, "email", None),
    )

    return product


@transaction.atomic
def reactivate_product(user, product, reason=""):
    product = Product.objects.select_for_update().get(pk=product.pk)
    if product.is_active:
        return product

    product.is_active = True
    _save_product(product, update_fields=["is_active", "updated_at"])
    _log_change(
        product,
        user,
        ProductChangeLog.Action.REACTIVATED,
        {},
        reason=reason,
    )

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


def get_catalog_updated_at(active_only=True):
    queryset = Product.objects.all()
    if active_only:
        queryset = queryset.active()
    return queryset.aggregate(latest=Max("updated_at"))["latest"]


def get_product_history(product):
    return product.change_logs.select_related("user").order_by("-created_at")


SUPPLIER_UPDATABLE_FIELDS = (
    "name",
    "contact_name",
    "email",
    "phone",
    "notes",
    "is_active",
)


def create_supplier(name, contact_name="", email="", phone="", notes=""):
    supplier = Supplier(
        name=name.strip(),
        contact_name=contact_name.strip(),
        email=email.strip(),
        phone=phone.strip(),
        notes=notes.strip(),
        is_active=True,
    )
    supplier.save()

    logger.info(
        "Created supplier id=%s name=%r",
        supplier.id,
        supplier.name,
    )

    return supplier


@transaction.atomic
def update_supplier(supplier, **fields):
    if not fields:
        return supplier

    unknown = set(fields) - set(SUPPLIER_UPDATABLE_FIELDS)
    if unknown:
        raise ValueError(f"Cannot update fields: {', '.join(sorted(unknown))}")

    supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)

    update_fields = []
    for field_name, new_value in fields.items():
        if field_name in ("name", "contact_name", "email", "phone", "notes"):
            new_value = new_value.strip()
        old_value = getattr(supplier, field_name)
        if old_value != new_value:
            setattr(supplier, field_name, new_value)
            update_fields.append(field_name)

    if not update_fields:
        return supplier

    update_fields.append("updated_at")
    supplier.save(update_fields=update_fields)

    logger.info(
        "Updated supplier id=%s fields=%s",
        supplier.id,
        update_fields,
    )

    return supplier


def get_suppliers(active_only=True):
    queryset = Supplier.objects.all()
    if active_only:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("name")


def get_suppliers_for_product(product, active_only=True):
    queryset = Supplier.objects.filter(product_suppliers__product=product)
    if active_only:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("name")


def get_products_for_supplier(supplier, active_only=True):
    queryset = Product.objects.filter(product_suppliers__supplier=supplier)
    if active_only:
        queryset = queryset.active()
    return queryset.order_by("id")


@transaction.atomic
def link_product_supplier(product, supplier):
    link, created = ProductSupplier.objects.get_or_create(
        product=product,
        supplier=supplier,
    )

    if created:
        logger.info(
            "Linked product id=%s to supplier id=%s",
            product.id,
            supplier.id,
        )

    return link


@transaction.atomic
def unlink_product_supplier(product, supplier):
    deleted, _ = ProductSupplier.objects.filter(
        product=product,
        supplier=supplier,
    ).delete()

    if deleted:
        logger.info(
            "Unlinked product id=%s from supplier id=%s",
            product.id,
            supplier.id,
        )
