from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Max

from logging_utils import get_logger

from .models import Product, ProductChangeLog, ProductFamily, ProductSupplier, Supplier

logger = get_logger("centcompras.products")

UPDATABLE_FIELDS = (
    "family",
    "internal_code",
    "description",
    "stock",
    "price",
    "unit_of_measure",
    "reorder_level",
)


class DuplicateInternalCodeError(ValidationError):
    def __init__(self, internal_code):
        super().__init__(
            f'Internal code "{internal_code}" is already used by another product.',
            code="duplicate_internal_code",
        )


class DeactivateReasonRequiredError(ValidationError):
    def __init__(self):
        super().__init__(
            "A reason is required to deactivate a product.",
            code="deactivate_reason_required",
        )


class ReactivateReasonRequiredError(ValidationError):
    def __init__(self):
        super().__init__(
            "A reason is required to activate a product.",
            code="reactivate_reason_required",
        )


class FamilyNameRequiredError(ValidationError):
    def __init__(self):
        super().__init__(
            "Family name is required.",
            code="family_name_required",
        )


class DuplicateFamilyNameError(ValidationError):
    def __init__(self, name):
        super().__init__(
            f'Family name "{name}" is already used.',
            code="duplicate_family_name",
        )


class SupplierNameRequiredError(ValidationError):
    def __init__(self):
        super().__init__(
            "Supplier name is required.",
            code="supplier_name_required",
        )


class DuplicateSupplierNameError(ValidationError):
    def __init__(self, name):
        super().__init__(
            f'Supplier name "{name}" is already used.',
            code="duplicate_supplier_name",
        )


class InvalidSupplierEmailError(ValidationError):
    def __init__(self):
        super().__init__(
            "Enter a valid email address.",
            code="invalid_supplier_email",
        )


def _serialize_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, ProductFamily):
        return {"id": value.pk, "name": value.name}
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


def _resolve_family(family):
    if isinstance(family, ProductFamily):
        return family
    return ProductFamily.objects.get(pk=family)


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
def create_product(
    user,
    family,
    description,
    stock,
    price,
    unit_of_measure,
    internal_code="",
    reorder_level="0",
    reason="",
    supplier_ids=None,
):
    internal_code = _normalize_internal_code(internal_code)
    validate_internal_code_available(internal_code)
    family = _resolve_family(family)

    product = Product(
        family=family,
        internal_code=internal_code,
        description=description,
        stock=Decimal(str(stock)),
        price=Decimal(str(price)),
        unit_of_measure=unit_of_measure,
        reorder_level=Decimal(str(reorder_level)),
        is_active=False,
    )
    _save_product(product, update_fields=None)

    _log_change(
        product,
        user,
        ProductChangeLog.Action.CREATED,
        {
            "family": _serialize_value(product.family),
            "internal_code": _serialize_value(product.internal_code),
            "description": product.description,
            "stock": _serialize_value(product.stock),
            "price": _serialize_value(product.price),
            "unit_of_measure": product.unit_of_measure,
            "reorder_level": _serialize_value(product.reorder_level),
        },
        reason=reason,
    )

    logger.info(
        "Created product id=%s internal_code=%r description=%r family=%s stock=%s price=%s user=%s",
        product.id,
        product.internal_code,
        product.description,
        product.family.name,
        product.stock,
        product.price,
        getattr(user, "email", None),
    )

    if supplier_ids is not None:
        set_product_suppliers(product, supplier_ids)

    return product


@transaction.atomic
def update_product(user, product, reason="", supplier_ids=None, **fields):
    if not fields and supplier_ids is None:
        return product

    if fields:
        unknown = set(fields) - set(UPDATABLE_FIELDS)
        if unknown:
            raise ValueError(f"Cannot update fields: {', '.join(sorted(unknown))}")

    product = Product.objects.select_for_update().get(pk=product.pk)

    if fields:
        changes = {}
        pending_internal_code = None

        for field_name, new_value in fields.items():
            if field_name in ("stock", "price", "reorder_level"):
                new_value = Decimal(str(new_value))
            elif field_name == "internal_code":
                new_value = _normalize_internal_code(new_value)
                pending_internal_code = new_value
            elif field_name == "family":
                new_value = _resolve_family(new_value)

            old_value = getattr(product, field_name)
            if old_value != new_value:
                changes[field_name] = {
                    "old": _serialize_value(old_value),
                    "new": _serialize_value(new_value),
                }
                setattr(product, field_name, new_value)

        if changes:
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

    if supplier_ids is not None:
        set_product_suppliers(product, supplier_ids)

    return product


@transaction.atomic
def deactivate_product(user, product, reason=""):
    product = Product.objects.select_for_update().get(pk=product.pk)
    if not product.is_active:
        return product

    reason = (reason or "").strip()
    if not reason:
        raise DeactivateReasonRequiredError()

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

    reason = (reason or "").strip()
    if not reason:
        raise ReactivateReasonRequiredError()

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


def get_products(active_only=True, family=None):
    queryset = Product.objects.select_related("family").order_by("id")
    if active_only:
        queryset = queryset.active()
    if family is not None:
        family = _resolve_family(family)
        queryset = queryset.filter(family=family)
    return queryset


def get_catalog_updated_at(active_only=True):
    queryset = Product.objects.all()
    if active_only:
        queryset = queryset.active()
    return queryset.aggregate(latest=Max("updated_at"))["latest"]


def get_product_history(product):
    return product.change_logs.select_related("user").order_by("-created_at")


FAMILY_UPDATABLE_FIELDS = ("name", "is_active")


def _normalize_family_name(name):
    return (name or "").strip()


def validate_family_name_available(name, exclude_family_id=None):
    name = _normalize_family_name(name)
    if not name:
        raise FamilyNameRequiredError()

    queryset = ProductFamily.objects.filter(name__iexact=name)
    if exclude_family_id is not None:
        queryset = queryset.exclude(pk=exclude_family_id)
    if queryset.exists():
        raise DuplicateFamilyNameError(name)
    return name


def _save_family(family, update_fields=None):
    try:
        if update_fields is None:
            family.save()
        else:
            family.save(update_fields=update_fields)
    except IntegrityError as exc:
        message = str(exc).lower()
        if "productfamily_name" in message or "unique_productfamily_name_ci" in message:
            raise DuplicateFamilyNameError(family.name) from exc
        raise


def create_product_family(name, is_active=True):
    name = validate_family_name_available(name)
    family = ProductFamily(
        name=name,
        is_active=is_active,
    )
    _save_family(family, update_fields=None)

    logger.info(
        "Created product family id=%s name=%r",
        family.id,
        family.name,
    )

    return family


@transaction.atomic
def update_product_family(family, **fields):
    if not fields:
        return family

    unknown = set(fields) - set(FAMILY_UPDATABLE_FIELDS)
    if unknown:
        raise ValueError(f"Cannot update fields: {', '.join(sorted(unknown))}")

    family = ProductFamily.objects.select_for_update().get(pk=family.pk)

    update_fields = []
    for field_name, new_value in fields.items():
        if field_name == "name":
            new_value = validate_family_name_available(
                new_value,
                exclude_family_id=family.pk,
            )
        old_value = getattr(family, field_name)
        if old_value != new_value:
            setattr(family, field_name, new_value)
            update_fields.append(field_name)

    if not update_fields:
        return family

    update_fields.append("updated_at")
    _save_family(family, update_fields=update_fields)

    logger.info(
        "Updated product family id=%s fields=%s",
        family.id,
        update_fields,
    )

    return family


def get_product_families(active_only=True):
    queryset = ProductFamily.objects.all()
    if active_only:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("name")


SUPPLIER_UPDATABLE_FIELDS = (
    "name",
    "contact_name",
    "email",
    "phone",
    "notes",
    "is_active",
)


def _normalize_supplier_name(name):
    return (name or "").strip()


def validate_supplier_name_available(name, exclude_supplier_id=None):
    name = _normalize_supplier_name(name)
    if not name:
        raise SupplierNameRequiredError()

    queryset = Supplier.objects.filter(name__iexact=name)
    if exclude_supplier_id is not None:
        queryset = queryset.exclude(pk=exclude_supplier_id)
    if queryset.exists():
        raise DuplicateSupplierNameError(name)
    return name


def _normalize_supplier_email(email):
    email = (email or "").strip()
    if not email:
        return ""
    try:
        validate_email(email)
    except ValidationError as exc:
        raise InvalidSupplierEmailError() from exc
    return email


def _save_supplier(supplier, update_fields=None):
    try:
        if update_fields is None:
            supplier.save()
        else:
            supplier.save(update_fields=update_fields)
    except IntegrityError as exc:
        message = str(exc).lower()
        if "unique_supplier_name_ci" in message or "supplier_name" in message:
            raise DuplicateSupplierNameError(supplier.name) from exc
        raise


def create_supplier(name, contact_name="", email="", phone="", notes=""):
    name = validate_supplier_name_available(name)
    supplier = Supplier(
        name=name,
        contact_name=(contact_name or "").strip(),
        email=_normalize_supplier_email(email),
        phone=(phone or "").strip(),
        notes=(notes or "").strip(),
        is_active=True,
    )
    _save_supplier(supplier, update_fields=None)

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
        if field_name == "name":
            new_value = validate_supplier_name_available(
                new_value,
                exclude_supplier_id=supplier.pk,
            )
        elif field_name == "email":
            new_value = _normalize_supplier_email(new_value)
        elif field_name in ("contact_name", "phone", "notes"):
            new_value = (new_value or "").strip()
        old_value = getattr(supplier, field_name)
        if old_value != new_value:
            setattr(supplier, field_name, new_value)
            update_fields.append(field_name)

    if not update_fields:
        return supplier

    update_fields.append("updated_at")
    _save_supplier(supplier, update_fields=update_fields)

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


@transaction.atomic
def set_product_suppliers(product, supplier_ids):
    wanted_ids = {int(supplier_id) for supplier_id in supplier_ids}
    suppliers = {
        supplier.id: supplier
        for supplier in Supplier.objects.filter(pk__in=wanted_ids)
    }
    missing = wanted_ids - set(suppliers)
    if missing:
        raise ValidationError(
            f"Unknown supplier ids: {', '.join(str(item) for item in sorted(missing))}"
        )

    current_ids = set(
        ProductSupplier.objects.filter(product=product).values_list(
            "supplier_id",
            flat=True,
        )
    )

    for supplier_id in wanted_ids - current_ids:
        link_product_supplier(product, suppliers[supplier_id])

    for supplier_id in current_ids - wanted_ids:
        try:
            supplier = Supplier.objects.get(pk=supplier_id)
        except ObjectDoesNotExist:
            continue
        unlink_product_supplier(product, supplier)
