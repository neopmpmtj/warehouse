from django.urls import path

from . import console_views


urlpatterns = [
    path(
        "manage/procurement/",
        console_views.procurement_console,
        name="procurement_console",
    ),
]
