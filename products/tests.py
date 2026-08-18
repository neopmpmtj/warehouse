import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from branches.models import Branch, BranchMembership
from products.models import Product, ProductChangeLog
from products.permissions import can_manage_catalog
from products.seed_catalog_data import PRODUCTS
from products.services import (
    DeactivateReasonRequiredError,
    ReactivateReasonRequiredError,
    DuplicateInternalCodeError,
    create_product,
    create_product_family,
    create_supplier,
    deactivate_product,
    get_catalog_updated_at,
    get_product_families,
    get_products,
    get_products_for_supplier,
    get_suppliers,
    get_suppliers_for_product,
    link_product_supplier,
    reactivate_product,
    set_product_suppliers,
    unlink_product_supplier,
    update_product,
    update_product_family,
    update_supplier,
    validate_internal_code_available,
)


class ProductTestCaseMixin:
    def create_test_family(self, name="Test Family"):
        return create_product_family(name)

    def create_test_product(self, user, family=None, active=True, **kwargs):
        if family is None:
            family = self.family
        defaults = {
            "family": family,
            "description": "Test product",
            "stock": "1",
            "price": "1.00",
            "unit_of_measure": Product.UnitOfMeasure.PIECE,
        }
        defaults.update(kwargs)
        product = create_product(user, **defaults)
        if active:
            reactivate_product(user, product, reason="Genesis")
            product.refresh_from_db()
        return product


class ProductServiceTests(ProductTestCaseMixin, TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="staff@example.com",
            password="test-pass-123",
            is_staff=True,
        )
        self.family = self.create_test_family()

    def test_create_product_writes_audit_log(self):
        product = create_product(
            self.user,
            family=self.family,
            description="Cement 50kg",
            stock="100",
            price="12.95",
            internal_code="CEM-50",
            unit_of_measure=Product.UnitOfMeasure.KG,
            reorder_level="20",
            reason="Initial stocktake",
        )

        log = product.change_logs.get(action=ProductChangeLog.Action.CREATED)

        self.assertEqual(log.action, ProductChangeLog.Action.CREATED)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.reason, "Initial stocktake")
        self.assertEqual(log.changes["description"], "Cement 50kg")
        self.assertEqual(log.changes["family"]["name"], self.family.name)
        self.assertEqual(log.changes["unit_of_measure"], Product.UnitOfMeasure.KG)
        self.assertFalse(product.is_active)

    def test_create_product_starts_inactive(self):
        product = create_product(
            self.user,
            family=self.family,
            description="New item",
            stock="1",
            price="1.00",
            unit_of_measure=Product.UnitOfMeasure.PIECE,
        )

        self.assertFalse(product.is_active)

    def test_update_product_detects_changes_after_in_memory_mutation(self):
        product = self.create_test_product(
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

    def test_update_product_audits_family_and_reorder_level(self):
        other_family = self.create_test_family("Other Family")
        product = self.create_test_product(
            self.user,
            description="Item",
            reorder_level="0",
        )

        update_product(
            self.user,
            product,
            family=other_family,
            reorder_level=Decimal("15"),
            unit_of_measure=Product.UnitOfMeasure.KG,
        )

        log = product.change_logs.latest("created_at")
        self.assertEqual(log.changes["family"]["new"]["name"], "Other Family")
        self.assertEqual(log.changes["reorder_level"]["new"], "15")
        self.assertEqual(log.changes["unit_of_measure"]["new"], Product.UnitOfMeasure.KG)

    def test_get_products_active_only_excludes_deactivated(self):
        active = self.create_test_product(self.user, description="Active item")
        inactive = self.create_test_product(self.user, description="Inactive item")
        deactivate_product(self.user, inactive, reason="Removed from catalogue")

        active_ids = list(get_products().values_list("id", flat=True))
        all_ids = list(get_products(active_only=False).values_list("id", flat=True))

        self.assertEqual(active_ids, [active.id])
        self.assertEqual(sorted(all_ids), sorted([active.id, inactive.id]))

    def test_get_products_filters_by_family(self):
        pipes = self.create_test_family("Pipes")
        cement = self.create_test_family("Cement")
        pipe_product = self.create_test_product(
            self.user,
            family=pipes,
            internal_code="PIPE-1",
            description="Pipe",
        )
        self.create_test_product(
            self.user,
            family=cement,
            internal_code="CEM-1",
            description="Cement",
        )

        pipe_ids = list(get_products(family=pipes).values_list("id", flat=True))

        self.assertEqual(pipe_ids, [pipe_product.id])

    def test_duplicate_internal_code_is_rejected(self):
        self.create_test_product(
            self.user,
            description="First",
            internal_code="PIPE-20",
        )

        with self.assertRaises(DuplicateInternalCodeError):
            validate_internal_code_available("PIPE-20")

        with self.assertRaises(DuplicateInternalCodeError):
            self.create_test_product(
                self.user,
                description="Second",
                internal_code="PIPE-20",
            )

    def test_update_product_rejects_duplicate_internal_code(self):
        self.create_test_product(
            self.user,
            description="First",
            internal_code="CODE-A",
        )
        second = self.create_test_product(
            self.user,
            description="Second",
            internal_code="CODE-B",
        )

        with self.assertRaises(DuplicateInternalCodeError):
            update_product(
                self.user,
                second,
                internal_code="CODE-A",
            )

    def test_get_catalog_updated_at_uses_latest_active_product(self):
        first = self.create_test_product(self.user, description="First")
        second = self.create_test_product(self.user, description="Second")

        update_product(
            self.user,
            first,
            stock=Decimal("5"),
        )
        second.refresh_from_db()
        first.refresh_from_db()

        self.assertEqual(get_catalog_updated_at(), first.updated_at)
        self.assertGreater(first.updated_at, second.updated_at)

        deactivate_product(self.user, first, reason="Removed from catalogue")
        self.assertEqual(get_catalog_updated_at(), second.updated_at)

    def test_get_catalog_updated_at_is_none_when_no_active_products(self):
        product = self.create_test_product(self.user, description="Only item")
        deactivate_product(self.user, product, reason="Removed from catalogue")

        self.assertIsNone(get_catalog_updated_at())
        self.assertEqual(get_products().count(), 0)

    def test_deactivate_and_reactivate_write_audit_logs(self):
        product = self.create_test_product(self.user, description="Lifecycle item")

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

    def test_deactivate_product_requires_reason(self):
        product = self.create_test_product(self.user, description="Needs a reason")

        with self.assertRaises(DeactivateReasonRequiredError):
            deactivate_product(self.user, product)

        with self.assertRaises(DeactivateReasonRequiredError):
            deactivate_product(self.user, product, reason="   ")

        product.refresh_from_db()
        self.assertTrue(product.is_active)

    def test_reactivate_product_requires_reason(self):
        product = create_product(
            self.user,
            family=self.family,
            description="Needs activation reason",
            stock="1",
            price="1.00",
            unit_of_measure=Product.UnitOfMeasure.PIECE,
        )

        with self.assertRaises(ReactivateReasonRequiredError):
            reactivate_product(self.user, product)

        with self.assertRaises(ReactivateReasonRequiredError):
            reactivate_product(self.user, product, reason="   ")

        product.refresh_from_db()
        self.assertFalse(product.is_active)

    def test_reactivate_already_active_does_not_require_reason(self):
        product = self.create_test_product(self.user, description="Already active")

        reactivate_product(self.user, product)

        product.refresh_from_db()
        self.assertTrue(product.is_active)
        self.assertEqual(
            product.change_logs.filter(action=ProductChangeLog.Action.REACTIVATED).count(),
            1,
        )

    def test_deactivate_already_inactive_does_not_require_reason(self):
        product = self.create_test_product(self.user, description="Already hidden")
        deactivate_product(self.user, product, reason="End of line")

        deactivate_product(self.user, product)

        product.refresh_from_db()
        self.assertFalse(product.is_active)
        self.assertEqual(
            product.change_logs.filter(action=ProductChangeLog.Action.DEACTIVATED).count(),
            1,
        )


class ProductFamilyServiceTests(TestCase):
    def test_get_product_families_active_only_excludes_inactive(self):
        active = create_product_family("Active Family")
        inactive = create_product_family("Inactive Family")
        update_product_family(inactive, is_active=False)

        names = list(get_product_families().values_list("name", flat=True))

        self.assertEqual(names, ["Active Family"])

    def test_update_product_family_changes_name(self):
        family = create_product_family("Original")

        updated = update_product_family(family, name="Renamed")

        self.assertEqual(updated.name, "Renamed")

    def test_create_product_family_respects_is_active(self):
        inactive = create_product_family("Inactive on create", is_active=False)

        self.assertFalse(inactive.is_active)
        self.assertEqual(get_product_families(active_only=False).count(), 1)
        self.assertEqual(get_product_families().count(), 0)


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


class ProductFamilyAdminAccessTests(TestCase):
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
            role=BranchMembership.Role.ADMIN,
        )
        self.client = Client()
        self.family_changelist_url = reverse("admin:products_productfamily_changelist")

    def test_staff_user_can_open_product_family_admin(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(self.family_changelist_url)

        self.assertEqual(response.status_code, 200)

    def test_branch_admin_cannot_open_product_family_admin(self):
        self.client.force_login(self.branch_user)

        response = self.client.get(self.family_changelist_url)

        self.assertIn(response.status_code, (302, 403))


class ProductApiTests(ProductTestCaseMixin, TestCase):
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
        self.family = self.create_test_family()

    def test_product_api_includes_catalog_updated_at(self):
        self.create_test_product(
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
        active = self.create_test_product(
            None,
            description="Still active",
        )
        inactive = self.create_test_product(
            None,
            description="Was active",
        )
        deactivate_product(None, inactive, reason="Removed from catalogue")

        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        product_ids = [product["id"] for product in payload["products"]]

        self.assertEqual(product_ids, [active.id])
        self.assertIsNotNone(payload["catalog_updated_at"])

    def test_product_api_returns_null_catalog_updated_at_when_empty(self):
        product = self.create_test_product(
            None,
            description="Temporary item",
        )
        deactivate_product(None, product, reason="Removed from catalogue")

        self.assertEqual(get_products().count(), 0)

        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["products"], [])
        self.assertIsNone(payload["catalog_updated_at"])

    def test_product_api_does_not_expose_family_or_uom(self):
        self.create_test_product(
            None,
            description="Branch visible only",
            unit_of_measure=Product.UnitOfMeasure.KG,
        )

        response = self.client.get(reverse("product_list"))
        payload = response.json()["products"][0]

        self.assertEqual(
            set(payload.keys()),
            {"id", "description", "stock", "price"},
        )


class SupplierServiceTests(ProductTestCaseMixin, TestCase):
    def setUp(self):
        self.staff_user = get_user_model().objects.create_user(
            email="staff@example.com",
            password="test-pass-123",
            is_staff=True,
        )
        self.family = self.create_test_family()

    def test_product_can_have_multiple_suppliers(self):
        product = self.create_test_product(
            self.staff_user,
            description="Cement 50kg",
            stock="100",
            price="12.95",
            internal_code="CEM-50",
            unit_of_measure=Product.UnitOfMeasure.KG,
        )
        first = create_supplier(name="BuildSupply Ltd", phone="+351 210 000 001")
        second = create_supplier(name="Porto Materials Co", email="sales@example.com")
        third = create_supplier(name="National Cement Works")

        link_product_supplier(product, first)
        link_product_supplier(product, second)
        link_product_supplier(product, third)

        supplier_names = list(
            get_suppliers_for_product(product).values_list("name", flat=True)
        )

        self.assertEqual(
            supplier_names,
            ["BuildSupply Ltd", "National Cement Works", "Porto Materials Co"],
        )

    def test_link_product_supplier_is_idempotent(self):
        product = self.create_test_product(self.staff_user, description="Pipe")
        supplier = create_supplier(name="BuildSupply Ltd")

        link_product_supplier(product, supplier)
        link_product_supplier(product, supplier)

        self.assertEqual(product.product_suppliers.count(), 1)

    def test_unlink_product_supplier_removes_link(self):
        product = self.create_test_product(self.staff_user, description="Pipe")
        supplier = create_supplier(name="BuildSupply Ltd")
        link_product_supplier(product, supplier)

        unlink_product_supplier(product, supplier)

        self.assertEqual(get_suppliers_for_product(product).count(), 0)

    def test_set_product_suppliers_replaces_links(self):
        product = self.create_test_product(self.staff_user, description="Pipe")
        first = create_supplier(name="BuildSupply Ltd")
        second = create_supplier(name="Porto Materials Co")
        third = create_supplier(name="National Cement Works")
        link_product_supplier(product, first)
        link_product_supplier(product, second)

        set_product_suppliers(product, [second.id, third.id])

        names = list(get_suppliers_for_product(product).values_list("name", flat=True))
        self.assertEqual(names, ["National Cement Works", "Porto Materials Co"])

    def test_update_product_locks_when_only_supplier_ids_change(self):
        product = self.create_test_product(self.staff_user, description="Pipe")
        first = create_supplier(name="BuildSupply Ltd")
        second = create_supplier(name="Porto Materials Co")
        set_product_suppliers(product, [first.id])

        updated = update_product(
            self.staff_user,
            product,
            supplier_ids=[second.id],
        )

        names = list(
            get_suppliers_for_product(updated).values_list("name", flat=True)
        )
        self.assertEqual(names, ["Porto Materials Co"])
        updated.refresh_from_db()
        self.assertEqual(updated.description, "Pipe")

    def test_create_product_rolls_back_when_supplier_ids_are_invalid(self):
        with self.assertRaises(ValidationError):
            self.create_test_product(
                self.staff_user,
                description="Should not persist",
                internal_code="SVC-FAIL",
                supplier_ids=[99999],
            )

        self.assertFalse(Product.objects.filter(internal_code="SVC-FAIL").exists())

    def test_get_products_for_supplier_returns_linked_products(self):
        product = self.create_test_product(
            self.staff_user,
            description="Cement",
            internal_code="CEM-50",
        )
        supplier = create_supplier(name="BuildSupply Ltd")
        link_product_supplier(product, supplier)

        product_ids = list(get_products_for_supplier(supplier).values_list("id", flat=True))

        self.assertEqual(product_ids, [product.id])

    def test_update_supplier_changes_contact_fields(self):
        supplier = create_supplier(name="BuildSupply Ltd")

        updated = update_supplier(
            supplier,
            contact_name="Ana Ribeiro",
            phone="+351 210 000 001",
        )

        self.assertEqual(updated.contact_name, "Ana Ribeiro")
        self.assertEqual(updated.phone, "+351 210 000 001")

    def test_get_suppliers_active_only_excludes_inactive(self):
        active = create_supplier(name="Active Supplier")
        inactive = create_supplier(name="Inactive Supplier")
        update_supplier(inactive, is_active=False)

        names = list(get_suppliers().values_list("name", flat=True))

        self.assertEqual(names, ["Active Supplier"])


class SupplierAdminAccessTests(TestCase):
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
            role=BranchMembership.Role.ADMIN,
        )
        self.client = Client()
        self.supplier_changelist_url = reverse("admin:products_supplier_changelist")

    def test_staff_user_can_open_supplier_admin(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(self.supplier_changelist_url)

        self.assertEqual(response.status_code, 200)

    def test_branch_admin_cannot_open_supplier_admin(self):
        self.client.force_login(self.branch_user)

        response = self.client.get(self.supplier_changelist_url)

        self.assertIn(response.status_code, (302, 403))


class ProductConsoleTests(ProductTestCaseMixin, TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            email="warehouse@example.com",
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
        self.family = self.create_test_family()

    def test_staff_without_branch_can_open_console(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("product_console"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "product-form")

    def test_branch_user_cannot_open_console(self):
        self.client.force_login(self.branch_user)

        response = self.client.get(reverse("product_console"))

        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("product_console"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_staff_login_redirects_to_console(self):
        response = self.client.post(
            reverse("login"),
            {"username": "warehouse@example.com", "password": "test-pass-123"},
        )

        self.assertRedirects(response, reverse("product_console"))

    def test_branch_user_cannot_use_manage_api(self):
        self.client.force_login(self.branch_user)

        response = self.client.get(reverse("manage_product_list"))

        self.assertEqual(response.status_code, 403)

    def test_staff_manage_api_includes_inactive_products(self):
        active = self.create_test_product(self.staff_user, description="Visible")
        inactive = self.create_test_product(
            self.staff_user,
            description="Hidden",
            active=False,
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("manage_product_list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        product_ids = [product["id"] for product in payload["products"]]
        self.assertEqual(sorted(product_ids), sorted([active.id, inactive.id]))
        self.assertIn("families", payload)
        self.assertIn("suppliers", payload)

    def test_staff_can_create_and_update_product_through_console_api(self):
        self.client.force_login(self.staff_user)
        supplier = create_supplier(name="BuildSupply Ltd")

        create_response = self.client.post(
            reverse("manage_product_list"),
            data=json.dumps({
                "family_id": self.family.id,
                "description": "Console cement",
                "stock": "12",
                "price": "9.50",
                "unit_of_measure": Product.UnitOfMeasure.KG,
                "internal_code": "CON-1",
                "reorder_level": "4",
                "reason": "Added from console",
                "supplier_ids": [supplier.id],
            }),
            content_type="application/json",
        )

        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()["product"]
        product = Product.objects.get(pk=created["id"])
        self.assertFalse(product.is_active)
        self.assertEqual(product.description, "Console cement")
        self.assertEqual(product.product_suppliers.count(), 1)
        self.assertEqual(
            product.change_logs.latest("created_at").reason,
            "Added from console",
        )

        activate_response = self.client.post(
            reverse("manage_product_reactivate", args=[product.id]),
            data=json.dumps({"reason": "Genesis"}),
            content_type="application/json",
        )
        self.assertEqual(activate_response.status_code, 200)
        product.refresh_from_db()
        self.assertTrue(product.is_active)

        update_response = self.client.patch(
            reverse("manage_product_detail", args=[product.id]),
            data=json.dumps({
                "description": "Console cement updated",
                "reason": "Corrected label",
                "supplier_ids": [],
            }),
            content_type="application/json",
        )

        self.assertEqual(update_response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.description, "Console cement updated")
        self.assertEqual(product.product_suppliers.count(), 0)
        self.assertEqual(
            product.change_logs.latest("created_at").reason,
            "Corrected label",
        )

    def test_console_create_rolls_back_when_supplier_ids_are_invalid(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("manage_product_list"),
            data=json.dumps({
                "family_id": self.family.id,
                "description": "Should not persist",
                "stock": "1",
                "price": "1.00",
                "unit_of_measure": Product.UnitOfMeasure.PIECE,
                "internal_code": "CON-FAIL",
                "supplier_ids": [99999],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Product.objects.filter(internal_code="CON-FAIL").exists())

    def test_console_update_rolls_back_when_supplier_ids_are_invalid(self):
        product = self.create_test_product(
            self.staff_user,
            description="Original label",
            internal_code="CON-KEEP",
        )
        supplier = create_supplier(name="BuildSupply Ltd")
        set_product_suppliers(product, [supplier.id])
        self.client.force_login(self.staff_user)

        response = self.client.patch(
            reverse("manage_product_detail", args=[product.id]),
            data=json.dumps({
                "description": "Should not persist",
                "supplier_ids": [99999],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        product.refresh_from_db()
        self.assertEqual(product.description, "Original label")
        self.assertEqual(product.product_suppliers.count(), 1)

    def test_staff_can_deactivate_through_console_api(self):
        product = self.create_test_product(self.staff_user, description="To hide")
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("manage_product_deactivate", args=[product.id]),
            data=json.dumps({"reason": "End of line"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertFalse(product.is_active)
        self.assertEqual(
            product.change_logs.latest("created_at").action,
            ProductChangeLog.Action.DEACTIVATED,
        )

    def test_console_deactivate_without_reason_is_rejected(self):
        product = self.create_test_product(self.staff_user, description="To hide")
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("manage_product_deactivate", args=[product.id]),
            data=json.dumps({"reason": ""}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["code"], "deactivate_reason_required")
        product.refresh_from_db()
        self.assertTrue(product.is_active)

    def test_console_reactivate_without_reason_is_rejected(self):
        product = self.create_test_product(
            self.staff_user,
            description="Inactive item",
            active=False,
        )
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("manage_product_reactivate", args=[product.id]),
            data=json.dumps({"reason": ""}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["code"], "reactivate_reason_required")
        product.refresh_from_db()
        self.assertFalse(product.is_active)

    def test_console_bulk_deactivate_without_reason_is_rejected(self):
        product = self.create_test_product(self.staff_user, description="To hide")
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("manage_product_bulk"),
            data=json.dumps({
                "action": "deactivate",
                "ids": [product.id],
                "reason": "",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "deactivate_reason_required")
        product.refresh_from_db()
        self.assertTrue(product.is_active)
