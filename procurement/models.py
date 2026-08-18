from django.conf import settings
from django.db import models

from products.models import Product, Supplier


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        APPROVED = "approved", "Approved"
        CANCELLED = "cancelled", "Cancelled"

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchase_orders_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_orders_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PO #{self.pk} ({self.supplier.name})"


class PurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="purchase_order_lines",
    )
    quantity_ordered = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["purchase_order", "product"],
                name="unique_po_product_line",
            ),
        ]

    def __str__(self):
        return f"PO {self.purchase_order_id} line {self.product_id}"


class GoodsReceipt(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name="receipts",
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="goods_receipts",
    )
    notes = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"Receipt #{self.pk} for PO {self.purchase_order_id}"


class GoodsReceiptLine(models.Model):
    receipt = models.ForeignKey(
        GoodsReceipt,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    po_line = models.ForeignKey(
        PurchaseOrderLine,
        on_delete=models.PROTECT,
        related_name="receipt_lines",
    )
    quantity_received = models.DecimalField(max_digits=12, decimal_places=3)

    def __str__(self):
        return f"Receipt line {self.po_line_id} qty {self.quantity_received}"
