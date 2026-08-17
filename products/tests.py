from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from branches.models import Branch, BranchMembership
from products.models import ProductChangeLog
from products.permissions import can_manage_catalog
from products.services import (
    DuplicateInternalCodeError,
    create_product,
    deactivate_product,
    get_catalog_updated_at,
    get_products,
    reactivate_product,
    update_product,
    validate_internal_code_available,
)


class ProductServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="staff@example.com",
            password="test-pass-123",
            is_staff=True,
        )

    def test_create_product_writes_audit_log(self):
        product = create_product(
            self.user,
            description="Cement 50kg",
            stock="100",
            price="12.95",
            internal_code="CEM-50",
            reason="Initial stocktake",
        )

        log = ProductChangeLog.objects.get(product=product)

        self.assertEqual(log.action, ProductChangeLog.Action.CREATED)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.reason, "Initial stocktake")
        self.assertEqual(log.changes["description"], "Cement 50kg")

    def test_update_product_detects_changes_after_in_memory_mutation(self):
        product = create_product(
            self.user,
            description="Original",
            stock="10",
            price="5.00",
        )

        product.description = "Updated"
        update_product(
            self.user,
            product,
            description="Updated",
            reason="Corrected label",
        )

        product.refresh_from_db()
        self.assertEqual(product.description, "Updated")

        log = product.change_logs.latest("created_at")
        self.assertEqual(log.action, ProductChangeLog.Action.UPDATED)
        self.assertEqual(log.reason, "Corrected label")
        self.assertEqual(log.changes["description"]["old"], "Original")
        self.assertEqual(log.changes["description"]["new"], "Updated")

    def test_get_products_active_only_excludes_deactivated(self):
        active = create_product(
            self.user,
            description="Active item",
            stock="1",
            price="1.00",
        )
        inactive = create_product(
            self.user,
            description="Inactive item",
            stock="1",
            price="1.00",
        )
        deactivate_product(self.user, inactive)

        active_ids = list(get_products().values_list("id", flat=True))
        all_ids = list(get_products(active_only=False).values_list("id", flat=True))

        self.assertEqual(active_ids, [active.id])
        self.assertEqual(sorted(all_ids), sorted([active.id, inactive.id]))

    def test_duplicate_internal_code_is_rejected(self):
        create_product(
            self.user,
            description="First",
            stock="1",
            price="1.00",
            internal_code="PIPE-20",
        )

        with self.assertRaises(DuplicateInternalCodeError):
            validate_internal_code_available("PIPE-20")

        with self.assertRaises(DuplicateInternalCodeError):
            create_product(
                self.user,
                description="Second",
                stock="1",
                price="1.00",
                internal_code="PIPE-20",
            )

    def test_update_product_rejects_duplicate_internal_code(self):
        create_product(
            self.user,
            description="First",
            stock="1",
            price="1.00",
            internal_code="CODE-A",
        )
        second = create_product(
            self.user,
            description="Second",
            stock="1",
            price="1.00",
            internal_code="CODE-B",
        )

        with self.assertRaises(DuplicateInternalCodeError):
            update_product(
                self.user,
                second,
                internal_code="CODE-A",
            )

    def test_get_catalog_updated_at_uses_latest_active_product(self):
        first = create_product(
            self.user,
            description="First",
            stock="1",
            price="1.00",
        )
        second = create_product(
            self.user,
            description="Second",
            stock="1",
            price="1.00",
        )

        update_product(
            self.user,
            first,
            stock=Decimal("5"),
        )
        second.refresh_from_db()
        first.refresh_from_db()

        self.assertEqual(get_catalog_updated_at(), first.updated_at)
        self.assertGreater(first.updated_at, second.updated_at)

        deactivate_product(self.user, first)
        self.assertEqual(get_catalog_updated_at(), second.updated_at)

    def test_get_catalog_updated_at_is_none_when_no_active_products(self):
        product = create_product(
            self.user,
            description="Only item",
            stock="1",
            price="1.00",
        )
        deactivate_product(self.user, product)

        self.assertIsNone(get_catalog_updated_at())
        self.assertEqual(get_products().count(), 0)

    def test_deactivate_and_reactivate_write_audit_logs(self):
        product = create_product(
            self.user,
            description="Lifecycle item",
            stock="1",
            price="1.00",
        )

        deactivate_product(self.user, product, reason="End of line")
        product.refresh_from_db()
        self.assertFalse(product.is_active)

        deactivated_log = product.change_logs.latest("created_at")
        self.assertEqual(deactivated_log.action, ProductChangeLog.Action.DEACTIVATED)
        self.assertEqual(deactivated_log.reason, "End of line")

        reactivate_product(self.user, product, reason="Back in stock")
        product.refresh_from_db()
        self.assertTrue(product.is_active)

        reactivated_log = product.change_logs.latest("created_at")
        self.assertEqual(reactivated_log.action, ProductChangeLog.Action.REACTIVATED)
        self.assertEqual(reactivated_log.reason, "Back in stock")


class ProductPermissionTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            email="staff@example.com",
            password="test-pass-123",
            is_staff=True,
        )
        self.branch_user = user_model.objects.create_user(
            email="branch@example.com",
            password="test-pass-123",
        )

    def test_can_manage_catalog_requires_staff(self):
        self.assertTrue(can_manage_catalog(self.staff_user))
        self.assertFalse(can_manage_catalog(self.branch_user))

    def test_anonymous_user_cannot_manage_catalog(self):
        anonymous = get_user_model()()
        self.assertFalse(can_manage_catalog(anonymous))


class ProductAdminAccessTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            email="staff@example.com",
            password="test-pass-123",
            is_staff=True,
        )
        self.branch_user = user_model.objects.create_user(
            email="branch@example.com",
            password="test-pass-123",
        )
        branch = Branch.objects.create(name="Test Branch")
        BranchMembership.objects.create(
            user=self.branch_user,
            branch=branch,
            role=BranchMembership.Role.USER,
        )
        self.client = Client()
        self.changelist_url = reverse("admin:products_product_changelist")

    def test_staff_user_can_open_product_admin(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(self.changelist_url)

        self.assertEqual(response.status_code, 200)

    def test_branch_user_cannot_open_product_admin(self):
        self.client.force_login(self.branch_user)

        response = self.client.get(self.changelist_url)

        self.assertIn(response.status_code, (302, 403))


class ProductApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="branch@example.com",
            password="test-pass-123",
        )
        branch = Branch.objects.create(name="Test Branch")
        BranchMembership.objects.create(
            user=self.user,
            branch=branch,
            role=BranchMembership.Role.USER,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_product_api_includes_catalog_updated_at(self):
        create_product(
            None,
            description="Visible product",
            stock="3",
            price="4.50",
        )

        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["products"]), 1)
        self.assertIsNotNone(payload["catalog_updated_at"])

    def test_product_api_requires_authentication(self):
        client = Client()

        response = client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "Authentication required")

    def test_product_api_excludes_deactivated_products(self):
        active = create_product(
            None,
            description="Still active",
            stock="1",
            price="1.00",
        )
        inactive = create_product(
            None,
            description="Was active",
            stock="1",
            price="1.00",
        )
        deactivate_product(None, inactive)

        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        product_ids = [product["id"] for product in payload["products"]]

        self.assertEqual(product_ids, [active.id])
        self.assertIsNotNone(payload["catalog_updated_at"])

    def test_product_api_returns_null_catalog_updated_at_when_empty(self):
        product = create_product(
            None,
            description="Temporary item",
            stock="1",
            price="1.00",
        )
        deactivate_product(None, product)

        self.assertEqual(get_products().count(), 0)

        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["products"], [])
        self.assertIsNone(payload["catalog_updated_at"])
