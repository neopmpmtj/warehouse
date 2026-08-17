from django.urls import path

from . import views


urlpatterns = [
    path("", views.product_page, name="product_page"),
    path(
        "service-worker.js",
        views.service_worker,
        name="service_worker",
    ),
]