from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from branches.models import Branch, BranchMembership
from products.models import Product, ProductFamily, Supplier
from products.seed_catalog_data import (
    FAMILIES,
    PRODUCT_SUPPLIER_LINKS,
    PRODUCTS,
    SUPPLIERS,
)
from products.services import (
    create_product,
    create_product_family,
    create_supplier,
    deactivate_product,
    link_product_supplier,
    update_product_family,
    update_supplier,
)


DEFAULT_PASSWORD = "devpass123"

BRANCHES = (
    "Lisbonbranch",
    "portobranch",
    "vilarealbranch",
)

BRANCH_USERS = (
    ("admin.lisbon@centcompras.dev", "Lisbonbranch"),
    ("admin.porto@centcompras.dev", "portobranch"),
    ("admin.vilareal@centcompras.dev", "vilarealbranch"),
)

WAREHOUSE_USER = ("warehouse@centcompras.dev",)


class Command(BaseCommand):
    help = (
        "Seed local dev data: branches, users, warehouse staff, product families, "
        "suppliers, ~50 products, and supplier links (idempotent)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help=f"Password for all seeded users (default: {DEFAULT_PASSWORD})",
        )
        parser.add_argument(
            "--skip-products",
            action="store_true",
            help="Only seed branches and users.",
        )
        parser.add_argument(
            "--skip-warehouse",
            action="store_true",
            help="Do not create the warehouse staff user (catalog admin).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]
        user_model = get_user_model()

        warehouse_user = None
        if not options["skip_warehouse"]:
            warehouse_user, created = user_model.objects.get_or_create(
                email=WAREHOUSE_USER[0],
                defaults={
                    "is_staff": True,
                    "is_superuser": False,
                },
            )
            if created or not warehouse_user.check_password(password):
                warehouse_user.set_password(password)
                warehouse_user.is_staff = True
                warehouse_user.save(update_fields=["password", "is_staff"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"Warehouse staff: {warehouse_user.email} (catalog admin at /manage/products/)"
                )
            )

        branches = {}
        for branch_name in BRANCHES:
            branch, created = Branch.objects.get_or_create(name=branch_name)
            branches[branch_name] = branch
            verb = "Created" if created else "Exists"
            self.stdout.write(f"{verb} branch: {branch.name}")

        for email, branch_name in BRANCH_USERS:
            user, created = user_model.objects.get_or_create(
                email=email,
                defaults={"is_staff": False, "is_superuser": False},
            )
            if created or not user.check_password(password):
                user.set_password(password)
                user.save(update_fields=["password"])

            membership, membership_created = BranchMembership.objects.get_or_create(
                user=user,
                branch=branches[branch_name],
                defaults={"role": BranchMembership.Role.ADMIN},
            )
            if membership.role != BranchMembership.Role.ADMIN:
                membership.role = BranchMembership.Role.ADMIN
                membership.save(update_fields=["role"])

            verb = "Created" if created else "Exists"
            self.stdout.write(
                f"{verb} branch admin: {email} -> {branch_name} "
                f"(membership {'created' if membership_created else 'exists'})"
            )

        if not options["skip_products"]:
            families_by_name = {}
            for family_data in FAMILIES:
                family, created = ProductFamily.objects.get_or_create(
                    name=family_data["name"],
                )
                if not family_data["is_active"] and family.is_active:
                    update_product_family(family, is_active=False)
                elif family_data["is_active"] and not family.is_active:
                    update_product_family(family, is_active=True)
                families_by_name[family.name] = family
                verb = "Created" if created else "Exists"
                self.stdout.write(f"{verb} family: {family.name}")

            suppliers_by_name = {}
            for supplier_data in SUPPLIERS:
                existing = Supplier.objects.filter(name=supplier_data["name"]).first()
                if existing:
                    supplier = existing
                    if supplier.is_active != supplier_data["is_active"]:
                        update_supplier(
                            supplier,
                            is_active=supplier_data["is_active"],
                        )
                    suppliers_by_name[supplier.name] = supplier
                    self.stdout.write(f"Exists supplier: {supplier.name}")
                    continue

                supplier = create_supplier(
                    name=supplier_data["name"],
                    contact_name=supplier_data.get("contact_name", ""),
                    email=supplier_data.get("email", ""),
                    phone=supplier_data.get("phone", ""),
                    notes=supplier_data.get("notes", ""),
                )
                if not supplier_data["is_active"]:
                    update_supplier(supplier, is_active=False)
                suppliers_by_name[supplier.name] = supplier
                self.stdout.write(
                    self.style.SUCCESS(f"Created supplier: {supplier.name}")
                )

            products_by_code = {}
            for row in PRODUCTS:
                (
                    internal_code,
                    description,
                    family_name,
                    unit,
                    stock,
                    price,
                    reorder_level,
                    is_active,
                ) = row
                family = families_by_name[family_name]
                existing = Product.objects.filter(internal_code=internal_code).first()
                if existing:
                    products_by_code[internal_code] = existing
                    self.stdout.write(
                        f"Exists product: {existing.internal_code} — {existing.description}"
                    )
                    continue

                product = create_product(
                    user=warehouse_user,
                    family=family,
                    description=description,
                    stock=stock,
                    price=Decimal(price),
                    unit_of_measure=unit,
                    internal_code=internal_code,
                    reorder_level=reorder_level,
                    reason="seed_dev_data",
                )
                if not is_active:
                    deactivate_product(warehouse_user, product, reason="seed_dev_data")
                products_by_code[internal_code] = product
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created product: {product.internal_code} — {product.description}"
                    )
                )

            for product_code, supplier_name in PRODUCT_SUPPLIER_LINKS:
                product = products_by_code.get(product_code)
                if product is None:
                    product = Product.objects.filter(internal_code=product_code).first()
                supplier = suppliers_by_name.get(supplier_name)
                if supplier is None:
                    supplier = Supplier.objects.filter(name=supplier_name).first()

                if product is None or supplier is None:
                    continue

                link_product_supplier(product, supplier)

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Dev login credentials (same password for all):"))
        self.stdout.write(f"  Password: {password}")
        self.stdout.write("")
        self.stdout.write("Branch catalogue login (phone UI at /):")
        for email, branch_name in BRANCH_USERS:
            self.stdout.write(f"  {email}  ->  {branch_name}")
        if warehouse_user:
            self.stdout.write("")
            self.stdout.write("Warehouse product management (/manage/products/):")
            self.stdout.write(f"  {warehouse_user.email}")
        self.stdout.write("")
        self.stdout.write(
            "Note: branch admin role controls future order permissions per branch. "
            "Product add/edit is warehouse staff only (is_staff), not branch role."
        )
