from django.urls import path

from . import views

urlpatterns = [
    path("select/", views.select_branch, name="select_branch"),
    path("no-access/", views.no_branch_access, name="no_branch_access"),
]
