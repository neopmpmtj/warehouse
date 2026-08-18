from django.contrib.auth import views as auth_views
from django.urls import reverse

from products.permissions import can_manage_catalog


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"

    def get_success_url(self):
        redirect_to = self.get_redirect_url()
        if redirect_to:
            return redirect_to
        if can_manage_catalog(self.request.user):
            return reverse("product_console")
        return super().get_success_url()
