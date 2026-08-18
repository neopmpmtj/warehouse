from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.exceptions import PermissionDenied, ValidationError
from django.template.response import TemplateResponse

from .models import Product, ProductChangeLog, ProductFamily, ProductSupplier, Supplier
from .permissions import can_manage_catalog
from .services import (
    DuplicateFamilyNameError,
    DuplicateInternalCodeError,
    DuplicateSupplierNameError,
    FamilyNameRequiredError,
    InvalidSupplierEmailError,
    SupplierNameRequiredError,
    create_product,
    create_product_family,
    create_supplier,
    deactivate_product,
    link_product_supplier,
    reactivate_product,
    unlink_product_supplier,
    update_product,
    update_product_family,
    update_supplier,
    validate_family_name_available,
    validate_internal_code_available,
    validate_supplier_name_available,
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
            "family",
            "internal_code",
            "description",
            "stock",
            "price",
            "unit_of_measure",
            "reorder_level",
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


class ProductSupplierInline(admin.TabularInline):
    model = ProductSupplier
    extra = 1
    autocomplete_fields = ("supplier",)

    def has_module_permission(self, request):
        return can_manage_catalog(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_catalog(request.user)

    def has_add_permission(self, request, obj=None):
        return can_manage_catalog(request.user)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return can_manage_catalog(request.user)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = (
        "id",
        "internal_code",
        "description",
        "family",
        "stock",
        "unit_of_measure",
        "reorder_level",
        "price",
        "supplier_count",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active", "family", "unit_of_measure")
    search_fields = ("internal_code", "description", "family__name")
    autocomplete_fields = ("family",)
    readonly_fields = ("is_active", "created_at", "updated_at")
    inlines = (ProductSupplierInline, ProductChangeLogInline)
    actions = ("deactivate_products", "reactivate_products")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "family",
                    "internal_code",
                    "description",
                    "stock",
                    "unit_of_measure",
                    "reorder_level",
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
        return super().get_queryset(request).include_inactive().select_related("family")

    @admin.display(description="Suppliers")
    def supplier_count(self, obj):
        return obj.product_suppliers.count()

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
                    family=form.cleaned_data["family"],
                    internal_code=form.cleaned_data["internal_code"],
                    description=form.cleaned_data["description"],
                    stock=form.cleaned_data["stock"],
                    price=form.cleaned_data["price"],
                    unit_of_measure=form.cleaned_data["unit_of_measure"],
                    reorder_level=form.cleaned_data["reorder_level"],
                )
                obj.pk = updated.pk
            else:
                created = create_product(
                    request.user,
                    family=form.cleaned_data["family"],
                    description=form.cleaned_data["description"],
                    stock=form.cleaned_data["stock"],
                    price=form.cleaned_data["price"],
                    unit_of_measure=form.cleaned_data["unit_of_measure"],
                    internal_code=form.cleaned_data.get("internal_code", ""),
                    reorder_level=form.cleaned_data["reorder_level"],
                    reason=reason,
                )
                obj.pk = created.pk
        except DuplicateInternalCodeError as exc:
            raise ValidationError({"internal_code": exc.messages[0]}) from exc

        obj.refresh_from_db()

    def save_formset(self, request, form, formset, change):
        if formset.model is ProductSupplier:
            if not can_manage_catalog(request.user):
                raise PermissionDenied

            product = form.instance
            if not product.pk:
                return

            for inline_form in formset.forms:
                if not inline_form.cleaned_data:
                    continue
                if inline_form.cleaned_data.get("DELETE"):
                    if inline_form.instance.pk:
                        unlink_product_supplier(
                            product,
                            inline_form.instance.supplier,
                        )
                elif inline_form.instance.pk is None:
                    supplier = inline_form.cleaned_data.get("supplier")
                    if supplier:
                        link_product_supplier(product, supplier)

            formset.save(commit=False)
            return

        super().save_formset(request, form, formset, change)

    @admin.action(description="Deactivate selected products")
    def deactivate_products(self, request, queryset):
        if request.POST.get("confirm_deactivate"):
            reason = request.POST.get("reason", "").strip()
            if not reason:
                self.message_user(
                    request,
                    "A reason is required to deactivate a product.",
                    messages.ERROR,
                )
                return None
            for product in queryset:
                deactivate_product(request.user, product, reason=reason)
            self.message_user(
                request,
                f"Deactivated {queryset.count()} product(s).",
            )
            return None

        return TemplateResponse(
            request,
            "admin/products/deactivate_reason.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "queryset": queryset,
                "action_checkbox_name": ACTION_CHECKBOX_NAME,
                "title": "Deactivate products",
            },
        )

    @admin.action(description="Reactivate selected products")
    def reactivate_products(self, request, queryset):
        for product in queryset:
            reactivate_product(request.user, product)


class SupplierProductInline(admin.TabularInline):
    model = ProductSupplier
    extra = 0
    autocomplete_fields = ("product",)
    readonly_fields = ("product",)

    def has_module_permission(self, request):
        return can_manage_catalog(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_catalog(request.user)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SupplierAdminForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = (
            "name",
            "contact_name",
            "email",
            "phone",
            "notes",
            "is_active",
        )

    def clean_name(self):
        exclude_supplier_id = self.instance.pk if self.instance.pk else None
        return validate_supplier_name_available(
            self.cleaned_data.get("name", ""),
            exclude_supplier_id=exclude_supplier_id,
        )


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    form = SupplierAdminForm
    list_display = (
        "name",
        "contact_name",
        "email",
        "phone",
        "product_count",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "contact_name", "email", "phone", "notes")
    readonly_fields = ("created_at", "updated_at")
    inlines = (SupplierProductInline,)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "contact_name",
                    "email",
                    "phone",
                    "notes",
                    "is_active",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Products")
    def product_count(self, obj):
        return obj.product_suppliers.count()

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

        try:
            if change:
                update_supplier(
                    obj,
                    name=form.cleaned_data["name"],
                    contact_name=form.cleaned_data["contact_name"],
                    email=form.cleaned_data["email"],
                    phone=form.cleaned_data["phone"],
                    notes=form.cleaned_data["notes"],
                    is_active=form.cleaned_data["is_active"],
                )
            else:
                created = create_supplier(
                    name=form.cleaned_data["name"],
                    contact_name=form.cleaned_data["contact_name"],
                    email=form.cleaned_data["email"],
                    phone=form.cleaned_data["phone"],
                    notes=form.cleaned_data["notes"],
                )
                obj.pk = created.pk
        except DuplicateSupplierNameError as exc:
            raise ValidationError({"name": exc.messages[0]}) from exc
        except SupplierNameRequiredError as exc:
            raise ValidationError({"name": exc.messages[0]}) from exc
        except InvalidSupplierEmailError as exc:
            raise ValidationError({"email": exc.messages[0]}) from exc

        obj.refresh_from_db()


class ProductFamilyProductInline(admin.TabularInline):
    model = Product
    extra = 0
    fields = ("internal_code", "description", "stock", "unit_of_measure", "is_active")
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ProductFamilyAdminForm(forms.ModelForm):
    class Meta:
        model = ProductFamily
        fields = ("name", "is_active")

    def clean_name(self):
        exclude_family_id = self.instance.pk if self.instance.pk else None
        return validate_family_name_available(
            self.cleaned_data.get("name", ""),
            exclude_family_id=exclude_family_id,
        )


@admin.register(ProductFamily)
class ProductFamilyAdmin(admin.ModelAdmin):
    form = ProductFamilyAdminForm
    list_display = ("name", "product_count", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (ProductFamilyProductInline,)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "is_active",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Products")
    def product_count(self, obj):
        return obj.products.count()

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

        try:
            if change:
                update_product_family(
                    obj,
                    name=form.cleaned_data["name"],
                    is_active=form.cleaned_data["is_active"],
                )
            else:
                created = create_product_family(
                    name=form.cleaned_data["name"],
                    is_active=form.cleaned_data["is_active"],
                )
                obj.pk = created.pk
        except DuplicateFamilyNameError as exc:
            raise ValidationError({"name": exc.messages[0]}) from exc
        except FamilyNameRequiredError as exc:
            raise ValidationError({"name": exc.messages[0]}) from exc

        obj.refresh_from_db()


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
