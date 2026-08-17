from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError

from .models import Product, ProductChangeLog
from .permissions import can_manage_catalog
from .services import (
    DuplicateInternalCodeError,
    create_product,
    deactivate_product,
    reactivate_product,
    update_product,
    validate_internal_code_available,
)


class ProductAdminForm(forms.ModelForm):
    audit_reason = forms.CharField(
        required=False,
        max_length=255,
        label="Reason (optional)",
        help_text="Optional note stored in the audit log for this change.",
    )

    class Meta:
        model = Product
        fields = (
            "internal_code",
            "description",
            "stock",
            "price",
        )

    def clean_internal_code(self):
        internal_code = self.cleaned_data.get("internal_code", "")
        exclude_product_id = self.instance.pk if self.instance.pk else None
        validate_internal_code_available(
            internal_code,
            exclude_product_id=exclude_product_id,
        )
        return internal_code


class ProductChangeLogInline(admin.TabularInline):
    model = ProductChangeLog
    extra = 0
    can_delete = False
    readonly_fields = ("user", "action", "reason", "changes", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = (
        "id",
        "internal_code",
        "description",
        "stock",
        "price",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("internal_code", "description")
    readonly_fields = ("is_active", "created_at", "updated_at")
    inlines = (ProductChangeLogInline,)
    actions = ("deactivate_products", "reactivate_products")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "internal_code",
                    "description",
                    "stock",
                    "price",
                    "is_active",
                    "created_at",
                    "updated_at",
                )
            },
        ),
        (
            "Audit",
            {"fields": ("audit_reason",)},
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).include_inactive()

    def has_module_permission(self, request):
        return can_manage_catalog(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_catalog(request.user)

    def has_add_permission(self, request):
        return can_manage_catalog(request.user)

    def has_change_permission(self, request, obj=None):
        return can_manage_catalog(request.user)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not can_manage_catalog(request.user):
            raise PermissionDenied

        reason = form.cleaned_data.get("audit_reason", "")

        try:
            if change:
                updated = update_product(
                    request.user,
                    obj,
                    reason=reason,
                    internal_code=form.cleaned_data["internal_code"],
                    description=form.cleaned_data["description"],
                    stock=form.cleaned_data["stock"],
                    price=form.cleaned_data["price"],
                )
                obj.pk = updated.pk
            else:
                created = create_product(
                    request.user,
                    description=form.cleaned_data["description"],
                    stock=form.cleaned_data["stock"],
                    price=form.cleaned_data["price"],
                    internal_code=form.cleaned_data.get("internal_code", ""),
                    reason=reason,
                )
                obj.pk = created.pk
        except DuplicateInternalCodeError as exc:
            raise ValidationError({"internal_code": exc.messages}) from exc

        obj.refresh_from_db()

    @admin.action(description="Deactivate selected products")
    def deactivate_products(self, request, queryset):
        for product in queryset:
            deactivate_product(request.user, product)

    @admin.action(description="Reactivate selected products")
    def reactivate_products(self, request, queryset):
        for product in queryset:
            reactivate_product(request.user, product)


@admin.register(ProductChangeLog)
class ProductChangeLogAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "user", "action", "reason", "created_at")
    list_filter = ("action",)
    search_fields = (
        "product__description",
        "product__internal_code",
        "user__email",
        "reason",
    )
    readonly_fields = ("product", "user", "action", "reason", "changes", "created_at")
    ordering = ("-created_at",)

    def has_module_permission(self, request):
        return can_manage_catalog(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_catalog(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
