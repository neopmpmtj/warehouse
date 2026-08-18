import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from products.models import Product, ProductFamily, StockMovement
from products.services import (
    apply_stock_change,
    create_product,
    create_product_family,
    create_supplier,
    reactivate_product,
    update_product_prices,
)
from procurement.models import PurchaseOrder
from procurement.services import (
    ApprovalPermissionError,
    approve_purchase_order,
    create_goods_receipt,
    create_purchase_order,
    set_purchase_order_lines,
    submit_purchase_order,
)


class ProcurementServiceTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            email="staff@example.com",
            password="test-pass-123",
            is_staff=True,
        )
        self.superuser = get_user_model().objects.create_user(
            email="super@example.com",
            password="test-pass-123",
            is_staff=True,
            is_superuser=True,
        )
        self.family = create_product_family("Cement")
        self.supplier = create_supplier(name="BuildSupply Ltd")
        self.product = create_product(
            self.staff,
            family=self.family,
            description="Cement 50kg",
            cost="8.00",
            price="12.95",
            internal_code="CEM-50",
            unit_of_measure=Product.UnitOfMeasure.KG,
        )
        reactivate_product(self.staff, self.product, reason="Genesis")

    def test_po_flow_submit_approve_receive_increases_stock(self):
        order = create_purchase_order(self.staff, self.supplier)
        set_purchase_order_lines(
            order,
            [{"product_id": self.product.id, "quantity_ordered": "10"}],
        )
        order = submit_purchase_order(order, self.staff)

        with self.assertRaises(ApprovalPermissionError):
            approve_purchase_order(order, self.staff)

        order = approve_purchase_order(order, self.superuser)
        self.assertEqual(order.status, PurchaseOrder.Status.APPROVED)
        line = order.lines.get()
        self.assertEqual(line.unit_cost, Decimal("8.00"))

        update_product_prices(self.staff, self.product, cost="9.00")
        line.refresh_from_db()
        self.assertEqual(line.unit_cost, Decimal("8.00"))

        self.assertEqual(self.product.stock, Decimal("0"))
        create_goods_receipt(
            order,
            [{"po_line_id": line.id, "quantity_received": "4"}],
            self.staff,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal("4"))
        self.assertTrue(
            StockMovement.objects.filter(
                product=self.product,
                quantity=Decimal("4"),
                source_type=StockMovement.SourceType.RECEIPT,
            ).exists()
        )

    def test_cannot_over_receive(self):
        order = create_purchase_order(self.staff, self.supplier)
        set_purchase_order_lines(
            order,
            [{"product_id": self.product.id, "quantity_ordered": "5"}],
        )
        order = submit_purchase_order(order, self.staff)
        order = approve_purchase_order(order, self.superuser)
        line = order.lines.get()

        from procurement.services import ProcurementError

        with self.assertRaises(ProcurementError):
            create_goods_receipt(
                order,
                [{"po_line_id": line.id, "quantity_received": "6"}],
                self.staff,
            )


class ProcurementConsoleApiTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            email="staff@example.com",
            password="test-pass-123",
            is_staff=True,
        )
        self.superuser = get_user_model().objects.create_user(
            email="super@example.com",
            password="test-pass-123",
            is_staff=True,
            is_superuser=True,
        )
        self.family = create_product_family("Cement")
        self.supplier = create_supplier(name="BuildSupply Ltd")
        self.product = create_product(
            self.staff,
            family=self.family,
            description="Cement 50kg",
            cost="8.00",
            price="12.95",
            internal_code="CEM-50",
            unit_of_measure=Product.UnitOfMeasure.KG,
        )
        reactivate_product(self.staff, self.product, reason="Genesis")
        self.client = Client()

    def _create_draft_po(self):
        response = self.client.post(
            reverse("manage_purchase_order_list"),
            data=json.dumps({
                "supplier_id": self.supplier.id,
                "notes": "Test PO",
                "lines": [
                    {"product_id": self.product.id, "quantity_ordered": "10"},
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["order"]

    def test_staff_cannot_approve_superuser_can(self):
        self.client.force_login(self.staff)
        order = self._create_draft_po()
        submit = self.client.post(
            reverse("manage_purchase_order_submit", args=[order["id"]]),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(submit.status_code, 200)

        denied = self.client.post(
            reverse("manage_purchase_order_approve", args=[order["id"]]),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_login(self.superuser)
        approved = self.client.post(
            reverse("manage_purchase_order_approve", args=[order["id"]]),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(
            approved.json()["order"]["status"],
            PurchaseOrder.Status.APPROVED,
        )

    def test_receive_endpoint_increases_stock(self):
        self.client.force_login(self.staff)
        order = self._create_draft_po()
        self.client.post(
            reverse("manage_purchase_order_submit", args=[order["id"]]),
            data="{}",
            content_type="application/json",
        )
        self.client.force_login(self.superuser)
        self.client.post(
            reverse("manage_purchase_order_approve", args=[order["id"]]),
            data="{}",
            content_type="application/json",
        )
        detail = self.client.get(
            reverse("manage_purchase_order_detail", args=[order["id"]]),
        )
        line_id = detail.json()["order"]["lines"][0]["id"]

        self.client.force_login(self.staff)
        receive = self.client.post(
            reverse("manage_purchase_order_receive", args=[order["id"]]),
            data=json.dumps({
                "lines": [{"po_line_id": line_id, "quantity_received": "3"}],
            }),
            content_type="application/json",
        )
        self.assertEqual(receive.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, Decimal("3"))


class StockLedgerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="staff@example.com",
            password="test-pass-123",
            is_staff=True,
        )
        self.family = create_product_family("Test")

    def test_apply_stock_change_updates_product_and_writes_movement(self):
        product = create_product(
            self.user,
            family=self.family,
            description="Item",
            price="1.00",
            cost="0.50",
            unit_of_measure=Product.UnitOfMeasure.PIECE,
        )
        apply_stock_change(self.user, product, "5", reason="Initial count")
        product.refresh_from_db()
        self.assertEqual(product.stock, Decimal("5"))
        movement = StockMovement.objects.get(product=product)
        self.assertEqual(movement.quantity, Decimal("5"))

    def test_update_product_prices_audits_cost_sell_wholesale(self):
        product = create_product(
            self.user,
            family=self.family,
            description="Item",
            price="1.00",
            cost="0.50",
            wholesale="0.75",
            unit_of_measure=Product.UnitOfMeasure.PIECE,
        )
        update_product_prices(
            self.user,
            product,
            cost="0.60",
            price="1.10",
            wholesale="0.80",
            reason="Price review",
        )
        product.refresh_from_db()
        self.assertEqual(product.cost, Decimal("0.60"))
        self.assertEqual(product.price, Decimal("1.10"))
        self.assertEqual(product.wholesale, Decimal("0.80"))
