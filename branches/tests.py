from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from branches.models import Branch, BranchMembership
from branches.permissions import (
    can_create_order,
    can_edit_or_delete_order,
    can_manage_branch_users,
)
from branches.session import ACTIVE_BRANCH_SESSION_KEY, get_active_branch, set_active_branch


class BranchSessionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="session@example.com",
            password="test-pass-123",
        )
        self.branch = Branch.objects.create(name="Session Branch")
        BranchMembership.objects.create(
            user=self.user,
            branch=self.branch,
            role=BranchMembership.Role.USER,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_set_and_get_active_branch(self):
        request = self.client.request().wsgi_request
        request.user = self.user
        request.session = self.client.session

        set_active_branch(request, self.branch)
        request.session.save()

        memberships = list(self.user.branch_memberships.select_related("branch"))
        self.assertEqual(get_active_branch(request, memberships), self.branch)

    def test_get_active_branch_ignores_invalid_session_branch(self):
        session = self.client.session
        session[ACTIVE_BRANCH_SESSION_KEY] = 99999
        session.save()

        request = self.client.request().wsgi_request
        request.user = self.user
        request.session = session

        memberships = list(self.user.branch_memberships.select_related("branch"))
        self.assertIsNone(get_active_branch(request, memberships))


class BranchMiddlewareTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_model = get_user_model()

    def test_user_without_membership_is_redirected_to_no_branch_page(self):
        user = self.user_model.objects.create_user(
            email="nobranch@example.com",
            password="test-pass-123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("product_page"))

        self.assertRedirects(response, reverse("no_branch_access"))

    def test_single_branch_user_is_auto_selected(self):
        user = self.user_model.objects.create_user(
            email="single@example.com",
            password="test-pass-123",
        )
        branch = Branch.objects.create(name="Only Branch")
        BranchMembership.objects.create(
            user=user,
            branch=branch,
            role=BranchMembership.Role.USER,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("product_page"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.session.get(ACTIVE_BRANCH_SESSION_KEY),
            branch.id,
        )

    def test_multi_branch_user_without_session_is_sent_to_picker(self):
        user = self.user_model.objects.create_user(
            email="multi@example.com",
            password="test-pass-123",
        )
        branch_a = Branch.objects.create(name="Branch A")
        branch_b = Branch.objects.create(name="Branch B")
        BranchMembership.objects.create(
            user=user,
            branch=branch_a,
            role=BranchMembership.Role.USER,
        )
        BranchMembership.objects.create(
            user=user,
            branch=branch_b,
            role=BranchMembership.Role.USER,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("product_page"))

        self.assertRedirects(response, reverse("select_branch"))


class BranchPermissionTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.branch = Branch.objects.create(name="Perm Branch")

    def _membership(self, role):
        user = self.user_model.objects.create_user(
            email=f"{role}@example.com",
            password="test-pass-123",
        )
        BranchMembership.objects.create(
            user=user,
            branch=self.branch,
            role=role,
        )
        return user

    def test_all_roles_can_create_orders(self):
        for role in BranchMembership.Role:
            user = self._membership(role)
            self.assertTrue(can_create_order(user, self.branch))

    def test_only_admin_can_edit_or_delete_orders(self):
        admin = self._membership(BranchMembership.Role.ADMIN)
        manager = self._membership(BranchMembership.Role.MANAGER)

        self.assertTrue(can_edit_or_delete_order(admin, self.branch))
        self.assertFalse(can_edit_or_delete_order(manager, self.branch))

    def test_only_admin_can_manage_branch_users(self):
        admin = self._membership(BranchMembership.Role.ADMIN)
        user = self._membership(BranchMembership.Role.USER)

        self.assertTrue(can_manage_branch_users(admin, self.branch))
        self.assertFalse(can_manage_branch_users(user, self.branch))

    def test_non_member_has_no_branch_permissions(self):
        outsider = self.user_model.objects.create_user(
            email="outsider@example.com",
            password="test-pass-123",
        )

        self.assertFalse(can_create_order(outsider, self.branch))
        self.assertFalse(can_edit_or_delete_order(outsider, self.branch))
        self.assertFalse(can_manage_branch_users(outsider, self.branch))


class SeedDevDataCommandTests(TestCase):
    def test_seed_dev_data_is_idempotent(self):
        from django.core.management import call_command

        from products.models import Product

        call_command("seed_dev_data")
        branch_count = Branch.objects.count()
        user_count = get_user_model().objects.count()
        product_count = Product.objects.count()

        call_command("seed_dev_data", skip_products=True)

        self.assertEqual(Branch.objects.count(), branch_count)
        self.assertEqual(get_user_model().objects.count(), user_count)
        self.assertEqual(Product.objects.count(), product_count)
        self.assertGreaterEqual(branch_count, 3)
        self.assertGreaterEqual(user_count, 4)
