from django.conf import settings
from django.db import models


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def include_inactive(self):
        return self


class ProductFamily(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    class UnitOfMeasure(models.TextChoices):
        PIECE = "piece", "Piece"
        KG = "kg", "Kilogram"
        G = "g", "Gram"
        M = "m", "Meter"
        M2 = "m2", "Square meter"
        M3 = "m3", "Cubic meter"
        L = "l", "Liter"

    family = models.ForeignKey(
        ProductFamily,
        on_delete=models.PROTECT,
        related_name="products",
    )
    internal_code = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=255)
    stock = models.DecimalField(max_digits=12, decimal_places=3)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    unit_of_measure = models.CharField(
        max_length=16,
        choices=UnitOfMeasure.choices,
        default=UnitOfMeasure.PIECE,
    )
    reorder_level = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["internal_code"],
                condition=~models.Q(internal_code=""),
                name="unique_product_internal_code_when_set",
            )
        ]

    def __str__(self):
        if self.internal_code:
            return f"{self.internal_code} — {self.description}"
        return self.description


class Supplier(models.Model):
    name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductSupplier(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="product_suppliers",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="product_suppliers",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "supplier"],
                name="unique_product_supplier",
            ),
        ]

    def __str__(self):
        return f"{self.product} — {self.supplier}"


class ProductChangeLog(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        DEACTIVATED = "deactivated", "Deactivated"
        REACTIVATED = "reactivated", "Reactivated"

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="change_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_change_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    changes = models.JSONField(default=dict)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product_id} {self.action} @ {self.created_at:%Y-%m-%d %H:%M}"
