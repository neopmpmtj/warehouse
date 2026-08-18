from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from logging_utils import get_logger

from products.models import Product, StockMovement, Supplier
from products.services import apply_stock_change

from .models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine

logger = get_logger("centcompras.procurement")


class ProcurementError(ValidationError):
    def __init__(self, message, code="procurement_error"):
        super().__init__(message, code=code)


class ApprovalPermissionError(PermissionDenied):
    pass


def _decimal(value, field_name):
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ProcurementError(f"{field_name} must be a number.") from exc


def _get_order(order_id, for_update=False):
    qs = PurchaseOrder.objects.select_related("supplier", "created_by", "approved_by")
    if for_update:
        # Lock only PurchaseOrder rows (approved_by is nullable — avoid outer-join FOR UPDATE).
        qs = qs.select_for_update(of=("self",))
    return qs.get(pk=order_id)


def _line_received_total(po_line):
    total = po_line.receipt_lines.aggregate(
        total=Sum("quantity_received"),
    )["total"]
    return total or Decimal("0")


def _order_has_receipts(order):
    return order.receipts.exists()


@transaction.atomic
def create_purchase_order(user, supplier, notes=""):
    if isinstance(supplier, Supplier):
        supplier_obj = supplier
    else:
        supplier_obj = Supplier.objects.get(pk=supplier)
    if not supplier_obj.is_active:
        raise ProcurementError("Supplier is not active.")

    order = PurchaseOrder.objects.create(
        supplier=supplier_obj,
        status=PurchaseOrder.Status.DRAFT,
        created_by=user,
        notes=(notes or "").strip(),
    )
    logger.info(
        "Created purchase order id=%s supplier=%s user=%s",
        order.id,
        supplier_obj.name,
        user.email,
    )
    return order


@transaction.atomic
def set_purchase_order_lines(order, line_items):
    order = _get_order(order.pk, for_update=True)
    if order.status not in (
        PurchaseOrder.Status.DRAFT,
        PurchaseOrder.Status.PENDING_APPROVAL,
    ):
        raise ProcurementError("Only draft or pending orders can be edited.")

    if not isinstance(line_items, list):
        raise ProcurementError("lines must be a list.")

    wanted_product_ids = set()
    for item in line_items:
        product_id = int(item["product_id"])
        qty = _decimal(item["quantity_ordered"], "quantity_ordered")
        if qty <= 0:
            raise ProcurementError("quantity_ordered must be greater than zero.")
        wanted_product_ids.add(product_id)

    products = {
        p.id: p
        for p in Product.objects.filter(pk__in=wanted_product_ids).select_related(
            "family",
        )
    }
    missing = wanted_product_ids - set(products)
    if missing:
        raise ProcurementError(
            f"Unknown product ids: {', '.join(str(i) for i in sorted(missing))}."
        )

    for product in products.values():
        if product.cost <= 0:
            raise ProcurementError(
                f"Product {product.internal_code or product.description} has no cost set."
            )

    current_lines = {line.product_id: line for line in order.lines.all()}
    for product_id in set(current_lines) - wanted_product_ids:
        current_lines[product_id].delete()

    for item in line_items:
        product_id = int(item["product_id"])
        product = products[product_id]
        qty = _decimal(item["quantity_ordered"], "quantity_ordered")
        unit_cost = product.cost
        if product_id in current_lines:
            line = current_lines[product_id]
            line.quantity_ordered = qty
            line.unit_cost = unit_cost
            line.save(update_fields=["quantity_ordered", "unit_cost"])
        else:
            PurchaseOrderLine.objects.create(
                purchase_order=order,
                product=product,
                quantity_ordered=qty,
                unit_cost=unit_cost,
            )

    order.save(update_fields=["updated_at"])
    return _get_order(order.pk)


@transaction.atomic
def submit_purchase_order(order, user):
    order = _get_order(order.pk, for_update=True)
    if order.status != PurchaseOrder.Status.DRAFT:
        raise ProcurementError("Only draft orders can be submitted.")

    lines = list(order.lines.select_related("product"))
    if not lines:
        raise ProcurementError("Add at least one line before submitting.")

    for line in lines:
        if line.quantity_ordered <= 0:
            raise ProcurementError("Every line must have a positive quantity.")
        if line.unit_cost <= 0:
            raise ProcurementError(
                f"Product {line.product_id} has no cost on the line."
            )
        line.unit_cost = line.product.cost
        line.save(update_fields=["unit_cost"])

    order.status = PurchaseOrder.Status.PENDING_APPROVAL
    order.save(update_fields=["status", "updated_at"])
    logger.info("Submitted PO id=%s user=%s", order.id, user.email)
    return _get_order(order.pk)


@transaction.atomic
def approve_purchase_order(order, user):
    if not user.is_superuser:
        raise ApprovalPermissionError("Only a superuser can approve purchase orders.")

    order = _get_order(order.pk, for_update=True)
    if order.status != PurchaseOrder.Status.PENDING_APPROVAL:
        raise ProcurementError("Only pending orders can be approved.")

    lines = list(order.lines.select_related("product"))
    if not lines:
        raise ProcurementError("Cannot approve an order with no lines.")

    for line in lines:
        if line.product.cost <= 0:
            raise ProcurementError(
                f"Product {line.product_id} has no cost set."
            )
        line.unit_cost = line.product.cost
        line.save(update_fields=["unit_cost"])

    order.status = PurchaseOrder.Status.APPROVED
    order.approved_by = user
    order.approved_at = timezone.now()
    order.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    logger.info("Approved PO id=%s user=%s", order.id, user.email)
    return _get_order(order.pk)


@transaction.atomic
def cancel_purchase_order(order, user):
    order = _get_order(order.pk, for_update=True)
    if order.status in (PurchaseOrder.Status.CANCELLED,):
        return order
    if order.status == PurchaseOrder.Status.APPROVED and _order_has_receipts(order):
        raise ProcurementError("Cannot cancel an approved order that has receipts.")
    if order.status not in (
        PurchaseOrder.Status.DRAFT,
        PurchaseOrder.Status.PENDING_APPROVAL,
        PurchaseOrder.Status.APPROVED,
    ):
        raise ProcurementError("This order cannot be cancelled.")

    order.status = PurchaseOrder.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    logger.info("Cancelled PO id=%s user=%s", order.id, user.email)
    return _get_order(order.pk)


@transaction.atomic
def create_goods_receipt(order, line_items, user):
    order = _get_order(order.pk, for_update=True)
    if order.status != PurchaseOrder.Status.APPROVED:
        raise ProcurementError("Only approved orders can be received.")

    if not isinstance(line_items, list) or not line_items:
        raise ProcurementError("lines must be a non-empty list.")

    receipt = GoodsReceipt.objects.create(
        purchase_order=order,
        received_by=user,
    )

    for item in line_items:
        po_line_id = int(item["po_line_id"])
        qty = _decimal(item["quantity_received"], "quantity_received")
        if qty <= 0:
            raise ProcurementError("quantity_received must be greater than zero.")

        try:
            po_line = PurchaseOrderLine.objects.select_related("product").get(
                pk=po_line_id,
                purchase_order=order,
            )
        except PurchaseOrderLine.DoesNotExist:
            raise ProcurementError(f"PO line {po_line_id} not found on this order.")

        received = _line_received_total(po_line)
        outstanding = po_line.quantity_ordered - received
        if qty > outstanding:
            raise ProcurementError(
                f"Cannot receive {qty} for product {po_line.product_id}; "
                f"outstanding is {outstanding}."
            )

        GoodsReceiptLine.objects.create(
            receipt=receipt,
            po_line=po_line,
            quantity_received=qty,
        )

        apply_stock_change(
            user,
            po_line.product,
            qty,
            reason=f"PO-{order.id} receipt",
            source_type=StockMovement.SourceType.RECEIPT,
            source_id=receipt.id,
        )

    logger.info(
        "Created goods receipt id=%s for PO id=%s user=%s",
        receipt.id,
        order.id,
        user.email,
    )
    return receipt


def get_purchase_orders():
    return PurchaseOrder.objects.select_related(
        "supplier",
        "created_by",
        "approved_by",
    ).prefetch_related(
        "lines__product",
        "lines__receipt_lines",
        "receipts",
    )


def line_quantity_received(po_line):
    return _line_received_total(po_line)


def line_quantity_outstanding(po_line):
    return po_line.quantity_ordered - _line_received_total(po_line)
