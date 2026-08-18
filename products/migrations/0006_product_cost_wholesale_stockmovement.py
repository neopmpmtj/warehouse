from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0005_family_supplier_changelog"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="cost",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="product",
            name="wholesale",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AlterField(
            model_name="product",
            name="stock",
            field=models.DecimalField(decimal_places=3, default=0, max_digits=12),
        ),
        migrations.CreateModel(
            name="StockMovement",
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
                ("quantity", models.DecimalField(decimal_places=3, max_digits=12)),
                ("reason", models.CharField(blank=True, max_length=255)),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("receipt", "Receipt"),
                            ("adjustment", "Adjustment"),
                            ("order", "Order"),
                        ],
                        max_length=20,
                    ),
                ),
                ("source_id", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stock_movements",
                        to="products.product",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="stock_movements",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
