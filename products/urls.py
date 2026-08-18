from django.urls import path

from . import console_views, views


urlpatterns = [
    path("products/", views.product_list, name="product_list"),
    path(
        "manage/families/",
        console_views.manage_family_list,
        name="manage_family_list",
    ),
    path(
        "manage/families/<int:family_id>/",
        console_views.manage_family_detail,
        name="manage_family_detail",
    ),
    path(
        "manage/families/<int:family_id>/history/",
        console_views.manage_family_history,
        name="manage_family_history",
    ),
    path(
        "manage/suppliers/",
        console_views.manage_supplier_list,
        name="manage_supplier_list",
    ),
    path(
        "manage/suppliers/<int:supplier_id>/",
        console_views.manage_supplier_detail,
        name="manage_supplier_detail",
    ),
    path(
        "manage/suppliers/<int:supplier_id>/history/",
        console_views.manage_supplier_history,
        name="manage_supplier_history",
    ),
    path(
        "manage/products/",
        console_views.manage_product_list,
        name="manage_product_list",
    ),
    path(
        "manage/products/bulk/",
        console_views.manage_product_bulk,
        name="manage_product_bulk",
    ),
    path(
        "manage/products/<int:product_id>/",
        console_views.manage_product_detail,
        name="manage_product_detail",
    ),
    path(
        "manage/products/<int:product_id>/deactivate/",
        console_views.manage_product_deactivate,
        name="manage_product_deactivate",
    ),
    path(
        "manage/products/<int:product_id>/reactivate/",
        console_views.manage_product_reactivate,
        name="manage_product_reactivate",
    ),
    path(
        "manage/products/<int:product_id>/history/",
        console_views.manage_product_history,
        name="manage_product_history",
    ),
]