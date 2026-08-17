from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),

    # API
    path("api/", include("products.urls")),

    # Web pages
    path("", include("products.web_urls")),
]