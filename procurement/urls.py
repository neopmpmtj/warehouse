from django.urls import path

from . import console_views


urlpatterns = [
    path(
        "manage/purchase-orders/",
        console_views.manage_purchase_order_list,
        name="manage_purchase_order_list",
    ),
    path(
        "manage/purchase-orders/catalog/",
        console_views.manage_procurement_catalog,
        name="manage_procurement_catalog",
    ),
    path(
        "manage/purchase-orders/<int:order_id>/",
        console_views.manage_purchase_order_detail,
        name="manage_purchase_order_detail",
    ),
    path(
        "manage/purchase-orders/<int:order_id>/submit/",
        console_views.manage_purchase_order_submit,
        name="manage_purchase_order_submit",
    ),
    path(
        "manage/purchase-orders/<int:order_id>/approve/",
        console_views.manage_purchase_order_approve,
        name="manage_purchase_order_approve",
    ),
    path(
        "manage/purchase-orders/<int:order_id>/cancel/",
        console_views.manage_purchase_order_cancel,
        name="manage_purchase_order_cancel",
    ),
    path(
        "manage/purchase-orders/<int:order_id>/receive/",
        console_views.manage_purchase_order_receive,
        name="manage_purchase_order_receive",
    ),
]
