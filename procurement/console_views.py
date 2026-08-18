import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from logging_utils import get_logger

from products.models import Product, Supplier
from products.permissions import staff_required
from products.services import get_suppliers

from .models import PurchaseOrder
from .services import (
    ApprovalPermissionError,
    ProcurementError,
    approve_purchase_order,
    cancel_purchase_order,
    create_goods_receipt,
    create_purchase_order,
    get_purchase_orders,
    line_quantity_outstanding,
    line_quantity_received,
    set_purchase_order_lines,
    submit_purchase_order,
)

logger = get_logger("centcompras.procurement")


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


def _serialize_supplier(supplier):
    return {
        "id": supplier.id,
        "name": supplier.name,
        "is_active": supplier.is_active,
    }


def _serialize_product_option(product):
    label = product.description
    if product.internal_code:
        label = f"{product.internal_code} — {product.description}"
    return {
        "id": product.id,
        "internal_code": product.internal_code,
        "description": product.description,
        "label": label,
        "cost": _decimal_string(product.cost),
        "is_active": product.is_active,
    }


def _serialize_line(line):
    received = line_quantity_received(line)
    outstanding = line_quantity_outstanding(line)
    return {
        "id": line.id,
        "product_id": line.product_id,
        "product_label": (
            f"{line.product.internal_code} — {line.product.description}"
            if line.product.internal_code
            else line.product.description
        ),
        "quantity_ordered": _decimal_string(line.quantity_ordered),
        "unit_cost": _decimal_string(line.unit_cost),
        "quantity_received": _decimal_string(received),
        "quantity_outstanding": _decimal_string(outstanding),
    }


def _serialize_order(order, user):
    can_approve = user.is_superuser and order.status == PurchaseOrder.Status.PENDING_APPROVAL
    can_receive = order.status == PurchaseOrder.Status.APPROVED
    can_edit = order.status in (
        PurchaseOrder.Status.DRAFT,
        PurchaseOrder.Status.PENDING_APPROVAL,
    )
    return {
        "id": order.id,
        "supplier": _serialize_supplier(order.supplier),
        "status": order.status,
        "notes": order.notes,
        "created_by_email": order.created_by.email,
        "approved_by_email": order.approved_by.email if order.approved_by_id else "",
        "approved_at": order.approved_at.isoformat() if order.approved_at else None,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
        "lines": [_serialize_line(line) for line in order.lines.all()],
        "receipt_count": order.receipts.count(),
        "can_approve": can_approve,
        "can_receive": can_receive,
        "can_edit": can_edit,
        "can_submit": order.status == PurchaseOrder.Status.DRAFT,
        "can_cancel": order.status in (
            PurchaseOrder.Status.DRAFT,
            PurchaseOrder.Status.PENDING_APPROVAL,
        ) or (
            order.status == PurchaseOrder.Status.APPROVED
            and not order.receipts.exists()
        ),
    }


def _procurement_error(exc):
    if isinstance(exc, ProcurementError):
        return _json_error(exc.messages[0], code=exc.code)
    if isinstance(exc, ApprovalPermissionError):
        return _json_error(str(exc), status=403, code="approval_forbidden")
    if isinstance(exc, ValidationError):
        message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
        return _json_error(message)
    if isinstance(exc, (PermissionDenied, ValueError, TypeError)):
        return _json_error(str(exc))
    raise exc


@staff_required
@require_GET
def procurement_console(request):
    return render(request, "procurement/procurement_console.html")


@staff_required
@require_GET
def manage_procurement_catalog(request):
    products = Product.objects.select_related("family").order_by("description")
    return JsonResponse(
        {
            "suppliers": [
                _serialize_supplier(s) for s in get_suppliers(active_only=True)
            ],
            "products": [_serialize_product_option(p) for p in products],
            "user_is_superuser": request.user.is_superuser,
        }
    )


@staff_required
@require_http_methods(["GET", "POST"])
def manage_purchase_order_list(request):
    if request.method == "GET":
        orders = get_purchase_orders()
        return JsonResponse(
            {
                "orders": [
                    _serialize_order(order, request.user) for order in orders
                ],
            }
        )

    try:
        payload = _parse_json(request)
        supplier_id = payload.get("supplier_id")
        if supplier_id is None:
            raise ValidationError("supplier_id is required.")
        order = create_purchase_order(
            request.user,
            supplier=int(supplier_id),
            notes=str(payload.get("notes", "")),
        )
        if "lines" in payload:
            order = set_purchase_order_lines(order, payload["lines"])
    except (ProcurementError, ValidationError) as exc:
        return _procurement_error(exc)

    order = get_purchase_orders().get(pk=order.pk)
    return JsonResponse({"order": _serialize_order(order, request.user)})


@staff_required
@require_http_methods(["GET", "PATCH"])
def manage_purchase_order_detail(request, order_id):
    try:
        order = get_purchase_orders().get(pk=order_id)
    except PurchaseOrder.DoesNotExist:
        return _json_error("Purchase order not found.", status=404)

    if request.method == "GET":
        return JsonResponse({"order": _serialize_order(order, request.user)})

    try:
        payload = _parse_json(request)
        if "supplier_id" in payload:
            if order.status not in (
                PurchaseOrder.Status.DRAFT,
                PurchaseOrder.Status.PENDING_APPROVAL,
            ):
                raise ProcurementError("This order cannot be edited.")
            supplier = Supplier.objects.get(pk=int(payload["supplier_id"]))
            if not supplier.is_active:
                raise ProcurementError("Supplier is not active.")
            order.supplier = supplier
            order.save(update_fields=["supplier", "updated_at"])
        if "notes" in payload:
            if order.status not in (
                PurchaseOrder.Status.DRAFT,
                PurchaseOrder.Status.PENDING_APPROVAL,
            ):
                raise ProcurementError("This order cannot be edited.")
            order.notes = str(payload.get("notes", "")).strip()
            order.save(update_fields=["notes", "updated_at"])
        if "lines" in payload:
            order = set_purchase_order_lines(order, payload["lines"])
    except (ProcurementError, ValidationError) as exc:
        return _procurement_error(exc)

    order = get_purchase_orders().get(pk=order.pk)
    return JsonResponse({"order": _serialize_order(order, request.user)})


@staff_required
@require_POST
def manage_purchase_order_submit(request, order_id):
    try:
        order = PurchaseOrder.objects.get(pk=order_id)
        order = submit_purchase_order(order, request.user)
    except PurchaseOrder.DoesNotExist:
        return _json_error("Purchase order not found.", status=404)
    except (ProcurementError, ValidationError) as exc:
        return _procurement_error(exc)

    order = get_purchase_orders().get(pk=order.pk)
    return JsonResponse({"order": _serialize_order(order, request.user)})


@staff_required
@require_POST
def manage_purchase_order_approve(request, order_id):
    try:
        order = PurchaseOrder.objects.get(pk=order_id)
        order = approve_purchase_order(order, request.user)
    except PurchaseOrder.DoesNotExist:
        return _json_error("Purchase order not found.", status=404)
    except (ProcurementError, ApprovalPermissionError, ValidationError) as exc:
        return _procurement_error(exc)

    order = get_purchase_orders().get(pk=order.pk)
    return JsonResponse({"order": _serialize_order(order, request.user)})


@staff_required
@require_POST
def manage_purchase_order_cancel(request, order_id):
    try:
        order = PurchaseOrder.objects.get(pk=order_id)
        order = cancel_purchase_order(order, request.user)
    except PurchaseOrder.DoesNotExist:
        return _json_error("Purchase order not found.", status=404)
    except (ProcurementError, ValidationError) as exc:
        return _procurement_error(exc)

    order = get_purchase_orders().get(pk=order.pk)
    return JsonResponse({"order": _serialize_order(order, request.user)})


@staff_required
@require_POST
def manage_purchase_order_receive(request, order_id):
    try:
        order = PurchaseOrder.objects.get(pk=order_id)
        payload = _parse_json(request)
        lines = payload.get("lines")
        if lines is None:
            raise ValidationError("lines is required.")
        receipt = create_goods_receipt(order, lines, request.user)
    except PurchaseOrder.DoesNotExist:
        return _json_error("Purchase order not found.", status=404)
    except (ProcurementError, ValidationError) as exc:
        return _procurement_error(exc)

    order = get_purchase_orders().get(pk=order_id)
    return JsonResponse(
        {
            "order": _serialize_order(order, request.user),
            "receipt_id": receipt.id,
        }
    )
