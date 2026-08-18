from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("products", "0006_product_cost_wholesale_stockmovement"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseOrder",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("pending_approval", "Pending approval"),
                            ("approved", "Approved"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="purchase_orders_approved",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="purchase_orders_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "supplier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="purchase_orders",
                        to="products.supplier",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PurchaseOrderLine",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "quantity_ordered",
                    models.DecimalField(decimal_places=3, max_digits=12),
                ),
                ("unit_cost", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="purchase_order_lines",
                        to="products.product",
                    ),
                ),
                (
                    "purchase_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="procurement.purchaseorder",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="GoodsReceipt",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                (
                    "purchase_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="receipts",
                        to="procurement.purchaseorder",
                    ),
                ),
                (
                    "received_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="goods_receipts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-received_at"],
            },
        ),
        migrations.CreateModel(
            name="GoodsReceiptLine",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "quantity_received",
                    models.DecimalField(decimal_places=3, max_digits=12),
                ),
                (
                    "po_line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="receipt_lines",
                        to="procurement.purchaseorderline",
                    ),
                ),
                (
                    "receipt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="procurement.goodsreceipt",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="purchaseorderline",
            constraint=models.UniqueConstraint(
                fields=("purchase_order", "product"),
                name="unique_po_product_line",
            ),
        ),
    ]
