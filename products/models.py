from django.conf import settings
from django.db import models


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def include_inactive(self):
        return self


class Product(models.Model):
    internal_code = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=255)
    stock = models.DecimalField(max_digits=12, decimal_places=3)
    price = models.DecimalField(max_digits=10, decimal_places=2)
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product_id} {self.action} @ {self.created_at:%Y-%m-%d %H:%M}"
