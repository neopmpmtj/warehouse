import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from logging_utils import get_logger

from .models import Product, ProductFamily, Supplier
from .permissions import staff_required
from .services import (
    DeactivateReasonRequiredError,
    DuplicateFamilyNameError,
    DuplicateInternalCodeError,
    DuplicateSupplierNameError,
    FamilyNameRequiredError,
    InvalidSupplierEmailError,
    ReactivateReasonRequiredError,
    SupplierNameRequiredError,
    create_product,
    create_product_family,
    create_supplier,
    deactivate_product,
    get_product_families,
    get_product_history,
    get_products,
    get_suppliers,
    reactivate_product,
    update_product,
    update_product_family,
    update_supplier,
)

logger = get_logger("centcompras.products")

VALID_UNITS = {choice[0] for choice in Product.UnitOfMeasure.choices}


def _json_error(message, status=400, code=None):
    payload = {"error": message}
    if code:
        payload["code"] = code
    return JsonResponse(payload, status=status)


def _parse_json(request):
    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        raise ValidationError("Request body must be valid JSON.")
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object.")
    return payload


def _decimal_string(value):
    return str(value)


def _serialize_family(family):
    payload = {
        "id": family.id,
        "name": family.name,
        "is_active": family.is_active,
    }
    product_count = getattr(family, "product_count", None)
    if product_count is not None:
        payload["product_count"] = product_count
    return payload


def _serialize_supplier(supplier):
    payload = {
        "id": supplier.id,
        "name": supplier.name,
        "contact_name": supplier.contact_name,
        "email": supplier.email,
        "phone": supplier.phone,
        "notes": supplier.notes,
        "is_active": supplier.is_active,
    }
    product_count = getattr(supplier, "product_count", None)
    if product_count is not None:
        payload["product_count"] = product_count
    return payload


def _serialize_product(product):
    suppliers = [
        _serialize_supplier(link.supplier)
        for link in product.product_suppliers.all()
    ]
    suppliers.sort(key=lambda item: item["name"].lower())
    return {
        "id": product.id,
        "internal_code": product.internal_code,
        "description": product.description,
        "stock": _decimal_string(product.stock),
        "price": _decimal_string(product.price),
        "unit_of_measure": product.unit_of_measure,
        "reorder_level": _decimal_string(product.reorder_level),
        "is_active": product.is_active,
        "family": _serialize_family(product.family),
        "suppliers": suppliers,
        "created_at": product.created_at.isoformat(),
        "updated_at": product.updated_at.isoformat(),
    }


def _serialize_history_entry(entry):
    user_email = ""
    if entry.user_id:
        user_email = entry.user.email
    return {
        "id": entry.id,
        "action": entry.action,
        "reason": entry.reason,
        "changes": entry.changes,
        "user_email": user_email,
        "created_at": entry.created_at.isoformat(),
    }


def _unit_choices():
    return [
        {"value": value, "label": label}
        for value, label in Product.UnitOfMeasure.choices
    ]


def _console_payload():
    products = get_products(active_only=False).prefetch_related(
        "product_suppliers__supplier",
    )
    return {
        "products": [_serialize_product(product) for product in products],
        "families": [
            _serialize_family(family)
            for family in _families_with_counts()
        ],
        "suppliers": [
            _serialize_supplier(supplier)
            for supplier in _suppliers_with_counts()
        ],
        "units": _unit_choices(),
    }


def _parse_decimal(payload, field_name, required=True):
    if field_name not in payload:
        if required:
            raise ValidationError(f"{field_name} is required.")
        return None
    try:
        return Decimal(str(payload[field_name]))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a number.") from exc


def _parse_unit(payload, required=True):
    if "unit_of_measure" not in payload:
        if required:
            raise ValidationError("unit_of_measure is required.")
        return None
    unit = str(payload["unit_of_measure"])
    if unit not in VALID_UNITS:
        raise ValidationError("unit_of_measure is not a valid choice.")
    return unit


def _parse_supplier_ids(payload):
    if "supplier_ids" not in payload:
        return None
    supplier_ids = payload["supplier_ids"]
    if not isinstance(supplier_ids, list):
        raise ValidationError("supplier_ids must be a list.")
    parsed = []
    for item in supplier_ids:
        try:
            parsed.append(int(item))
        except (TypeError, ValueError) as exc:
            raise ValidationError("supplier_ids must contain integers.") from exc
    return parsed


def _families_with_counts():
    return get_product_families(active_only=False).annotate(
        product_count=Count("products"),
    )


def _get_family(family_id):
    return _families_with_counts().get(pk=family_id)


def _family_response(family):
    family = _get_family(family.pk)
    return JsonResponse({"family": _serialize_family(family)})


def _suppliers_with_counts():
    return get_suppliers(active_only=False).annotate(
        product_count=Count("product_suppliers"),
    )


def _get_supplier(supplier_id):
    return _suppliers_with_counts().get(pk=supplier_id)


def _supplier_response(supplier):
    supplier = _get_supplier(supplier.pk)
    return JsonResponse({"supplier": _serialize_supplier(supplier)})


def _get_product(product_id):
    return (
        Product.objects.select_related("family")
        .prefetch_related("product_suppliers__supplier")
        .get(pk=product_id)
    )


def _product_response(product):
    product = _get_product(product.pk)
    return JsonResponse({"product": _serialize_product(product)})


@staff_required
@require_GET
def product_console(request):
    return render(request, "products/product_console.html")


@staff_required
@require_http_methods(["GET", "POST"])
def manage_product_list(request):
    if request.method == "GET":
        return JsonResponse(_console_payload())

    try:
        payload = _parse_json(request)
        description = str(payload.get("description", "")).strip()
        if not description:
            raise ValidationError("description is required.")
        family_id = payload.get("family_id")
        if family_id is None:
            raise ValidationError("family_id is required.")
        product = create_product(
            request.user,
            family=int(family_id),
            description=description,
            stock=_parse_decimal(payload, "stock"),
            price=_parse_decimal(payload, "price"),
            unit_of_measure=_parse_unit(payload),
            internal_code=str(payload.get("internal_code", "")),
            reorder_level=_parse_decimal(payload, "reorder_level")
            if "reorder_level" in payload
            else "0",
            reason=str(payload.get("reason", "")),
            supplier_ids=_parse_supplier_ids(payload),
        )
    except DuplicateInternalCodeError as exc:
        return _json_error(exc.messages[0])
    except (ValidationError, ObjectDoesNotExist, ValueError, TypeError) as exc:
        message = exc.messages[0] if isinstance(exc, ValidationError) and getattr(exc, "messages", None) else str(exc)
        return _json_error(message)

    logger.info("Console created product id=%s user=%s", product.id, request.user.email)
    return _product_response(product)


@staff_required
@require_http_methods(["GET", "PATCH"])
def manage_product_detail(request, product_id):
    try:
        product = _get_product(product_id)
    except Product.DoesNotExist:
        return _json_error("Product not found.", status=404)

    if request.method == "GET":
        return JsonResponse({"product": _serialize_product(product)})

    try:
        payload = _parse_json(request)
        fields = {}
        if "description" in payload:
            description = str(payload["description"]).strip()
            if not description:
                raise ValidationError("description is required.")
            fields["description"] = description
        if "internal_code" in payload:
            fields["internal_code"] = str(payload["internal_code"])
        if "family_id" in payload:
            fields["family"] = int(payload["family_id"])
        if "stock" in payload:
            fields["stock"] = _parse_decimal(payload, "stock")
        if "price" in payload:
            fields["price"] = _parse_decimal(payload, "price")
        if "unit_of_measure" in payload:
            fields["unit_of_measure"] = _parse_unit(payload)
        if "reorder_level" in payload:
            fields["reorder_level"] = _parse_decimal(payload, "reorder_level")

        product = update_product(
            request.user,
            product,
            reason=str(payload.get("reason", "")),
            supplier_ids=_parse_supplier_ids(payload),
            **fields,
        )
    except DuplicateInternalCodeError as exc:
        return _json_error(exc.messages[0])
    except (ValidationError, ObjectDoesNotExist, ValueError, TypeError) as exc:
        message = exc.messages[0] if isinstance(exc, ValidationError) and getattr(exc, "messages", None) else str(exc)
        return _json_error(message)

    logger.info("Console updated product id=%s user=%s", product.id, request.user.email)
    return _product_response(product)


@staff_required
@require_POST
def manage_product_deactivate(request, product_id):
    return _lifecycle(request, product_id, deactivate_product)


@staff_required
@require_POST
def manage_product_reactivate(request, product_id):
    return _lifecycle(request, product_id, reactivate_product)


def _lifecycle(request, product_id, action):
    try:
        product = _get_product(product_id)
        payload = _parse_json(request) if request.body else {}
        product = action(
            request.user,
            product,
            reason=str(payload.get("reason", "")),
        )
    except json.JSONDecodeError:
        return _json_error("Request body must be valid JSON.")
    except Product.DoesNotExist:
        return _json_error("Product not found.", status=404)
    except (DeactivateReasonRequiredError, ReactivateReasonRequiredError) as exc:
        return _json_error(exc.messages[0], code=exc.code)
    except ValidationError as exc:
        return _json_error(exc.messages[0] if exc.messages else str(exc))

    return _product_response(product)


@staff_required
@require_POST
def manage_product_bulk(request):
    try:
        payload = _parse_json(request)
        action_name = str(payload.get("action", "")).strip()
        if action_name not in {"deactivate", "reactivate"}:
            raise ValidationError("action must be deactivate or reactivate.")
        ids = payload.get("ids")
        if not isinstance(ids, list) or not ids:
            raise ValidationError("ids must be a non-empty list.")
        product_ids = [int(item) for item in ids]
    except (ValidationError, TypeError, ValueError) as exc:
        message = exc.messages[0] if isinstance(exc, ValidationError) and getattr(exc, "messages", None) else str(exc)
        return _json_error(message)

    action = deactivate_product if action_name == "deactivate" else reactivate_product
    reason = str(payload.get("reason", ""))
    products = list(
        Product.objects.filter(pk__in=product_ids).select_related("family")
    )
    found_ids = {product.id for product in products}
    missing = [item for item in product_ids if item not in found_ids]
    if missing:
        return _json_error(f"Product not found: {', '.join(str(item) for item in missing)}.", status=404)

    try:
        for product in products:
            action(request.user, product, reason=reason)
    except (DeactivateReasonRequiredError, ReactivateReasonRequiredError) as exc:
        return _json_error(exc.messages[0], code=exc.code)

    refreshed = (
        Product.objects.select_related("family")
        .prefetch_related("product_suppliers__supplier")
        .filter(pk__in=found_ids)
    )
    logger.info(
        "Console bulk %s ids=%s user=%s",
        action_name,
        product_ids,
        request.user.email,
    )
    return JsonResponse(
        {"products": [_serialize_product(product) for product in refreshed]}
    )


@staff_required
@require_GET
def manage_product_history(request, product_id):
    try:
        product = Product.objects.get(pk=product_id)
    except Product.DoesNotExist:
        return _json_error("Product not found.", status=404)

    entries = get_product_history(product)
    return JsonResponse(
        {"history": [_serialize_history_entry(entry) for entry in entries]}
    )


def _family_error(exc):
    if isinstance(exc, (FamilyNameRequiredError, DuplicateFamilyNameError)):
        return _json_error(exc.messages[0], code=exc.code)
    if isinstance(exc, ValidationError):
        message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
        return _json_error(message)
    if isinstance(exc, (ObjectDoesNotExist, ValueError, TypeError)):
        return _json_error(str(exc))
    raise exc


@staff_required
@require_http_methods(["GET", "POST"])
def manage_family_list(request):
    if request.method == "GET":
        return JsonResponse(
            {
                "families": [
                    _serialize_family(family) for family in _families_with_counts()
                ]
            }
        )

    try:
        payload = _parse_json(request)
        is_active = payload.get("is_active", True)
        if not isinstance(is_active, bool):
            raise ValidationError("is_active must be a boolean.")
        family = create_product_family(
            name=str(payload.get("name", "")),
            is_active=is_active,
        )
    except (FamilyNameRequiredError, DuplicateFamilyNameError, ValidationError) as exc:
        return _family_error(exc)

    logger.info("Console created family id=%s user=%s", family.id, request.user.email)
    return _family_response(family)


@staff_required
@require_http_methods(["GET", "PATCH"])
def manage_family_detail(request, family_id):
    try:
        family = _get_family(family_id)
    except ProductFamily.DoesNotExist:
        return _json_error("Family not found.", status=404)

    if request.method == "GET":
        return JsonResponse({"family": _serialize_family(family)})

    try:
        payload = _parse_json(request)
        fields = {}
        if "name" in payload:
            fields["name"] = str(payload["name"])
        if "is_active" in payload:
            if not isinstance(payload["is_active"], bool):
                raise ValidationError("is_active must be a boolean.")
            fields["is_active"] = payload["is_active"]
        family = update_product_family(family, **fields)
    except (FamilyNameRequiredError, DuplicateFamilyNameError, ValidationError) as exc:
        return _family_error(exc)

    logger.info("Console updated family id=%s user=%s", family.id, request.user.email)
    return _family_response(family)


def _supplier_error(exc):
    if isinstance(
        exc,
        (
            SupplierNameRequiredError,
            DuplicateSupplierNameError,
            InvalidSupplierEmailError,
        ),
    ):
        return _json_error(exc.messages[0], code=exc.code)
    if isinstance(exc, ValidationError):
        message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
        return _json_error(message)
    if isinstance(exc, (ObjectDoesNotExist, ValueError, TypeError)):
        return _json_error(str(exc))
    raise exc


@staff_required
@require_http_methods(["GET", "POST"])
def manage_supplier_list(request):
    if request.method == "GET":
        return JsonResponse(
            {
                "suppliers": [
                    _serialize_supplier(supplier)
                    for supplier in _suppliers_with_counts()
                ]
            }
        )

    try:
        payload = _parse_json(request)
        supplier = create_supplier(
            name=str(payload.get("name", "")),
            contact_name=str(payload.get("contact_name", "")),
            email=str(payload.get("email", "")),
            phone=str(payload.get("phone", "")),
            notes=str(payload.get("notes", "")),
        )
    except (
        SupplierNameRequiredError,
        DuplicateSupplierNameError,
        InvalidSupplierEmailError,
        ValidationError,
    ) as exc:
        return _supplier_error(exc)

    logger.info(
        "Console created supplier id=%s user=%s",
        supplier.id,
        request.user.email,
    )
    return _supplier_response(supplier)


@staff_required
@require_http_methods(["GET", "PATCH"])
def manage_supplier_detail(request, supplier_id):
    try:
        supplier = _get_supplier(supplier_id)
    except Supplier.DoesNotExist:
        return _json_error("Supplier not found.", status=404)

    if request.method == "GET":
        return JsonResponse({"supplier": _serialize_supplier(supplier)})

    try:
        payload = _parse_json(request)
        fields = {}
        for field_name in ("contact_name", "email", "phone", "notes"):
            if field_name in payload:
                fields[field_name] = str(payload[field_name])
        if "is_active" in payload:
            if not isinstance(payload["is_active"], bool):
                raise ValidationError("is_active must be a boolean.")
            fields["is_active"] = payload["is_active"]
        supplier = update_supplier(supplier, **fields)
    except (
        SupplierNameRequiredError,
        DuplicateSupplierNameError,
        InvalidSupplierEmailError,
        ValidationError,
    ) as exc:
        return _supplier_error(exc)

    logger.info(
        "Console updated supplier id=%s user=%s",
        supplier.id,
        request.user.email,
    )
    return _supplier_response(supplier)
