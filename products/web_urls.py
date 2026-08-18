from django.urls import path

from . import console_views, views


urlpatterns = [
    path("", views.product_page, name="product_page"),
    path(
        "manage/products/",
        console_views.product_console,
        name="product_console",
    ),
    path(
        "service-worker.js",
        views.service_worker,
        name="service_worker",
    ),
]