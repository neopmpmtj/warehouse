from django.contrib import admin
from django.core.exceptions import PermissionDenied

from .models import Product, ProductChangeLog
from .permissions import can_manage_catalog
from .services import (
    create_product,
    deactivate_product,
    reactivate_product,
    update_product,
)


class ProductChangeLogInline(admin.TabularInline):
    model = ProductChangeLog
    extra = 0
    can_delete = False
    readonly_fields = ("user", "action", "changes", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
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

        if change:
            updated = update_product(
                request.user,
                obj,
                internal_code=form.cleaned_data["internal_code"],
                description=form.cleaned_data["description"],
                stock=form.cleaned_data["stock"],
                price=form.cleaned_data["price"],
            )
            obj.pk = updated.pk
            obj.refresh_from_db()
        else:
            created = create_product(
                request.user,
                description=form.cleaned_data["description"],
                stock=form.cleaned_data["stock"],
                price=form.cleaned_data["price"],
                internal_code=form.cleaned_data.get("internal_code", ""),
            )
            obj.pk = created.pk
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
    list_display = ("id", "product", "user", "action", "created_at")
    list_filter = ("action",)
    search_fields = ("product__description", "product__internal_code", "user__email")
    readonly_fields = ("product", "user", "action", "changes", "created_at")
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
