from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from branches.models import Branch, BranchMembership
from products.models import Product, Supplier
from products.services import create_product, create_supplier, link_product_supplier


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

PRODUCTS = (
    {
        "description": "Cement 50kg",
        "stock": "100",
        "price": "12.95",
        "internal_code": "CEM-50",
    },
    {
        "description": "Steel Pipe 20mm",
        "stock": "50",
        "price": "8.75",
        "internal_code": "PIPE-20",
    },
    {
        "description": "Sand 1kg",
        "stock": "250.5",
        "price": "0.85",
        "internal_code": "SAND-1KG",
    },
)

SUPPLIERS = (
    {
        "name": "BuildSupply Ltd",
        "phone": "+351 210 000 001",
        "contact_name": "Ana Ribeiro",
    },
    {
        "name": "Porto Materials Co",
        "email": "sales@portomaterials.dev",
        "contact_name": "Carlos Mendes",
    },
    {
        "name": "National Cement Works",
        "phone": "+351 220 000 002",
        "contact_name": "Warehouse desk",
    },
)

PRODUCT_SUPPLIER_LINKS = (
    ("CEM-50", "BuildSupply Ltd"),
    ("CEM-50", "Porto Materials Co"),
    ("CEM-50", "National Cement Works"),
    ("PIPE-20", "BuildSupply Ltd"),
)


class Command(BaseCommand):
    help = (
        "Seed local dev data: 3 branches, 3 branch admin users, 1 warehouse staff user, "
        "and 3 sample products (idempotent)."
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
                    f"Warehouse staff: {warehouse_user.email} (catalog admin at /admin/products/)"
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
            product_user = warehouse_user
            products_by_code = {}
            for product_data in PRODUCTS:
                existing = Product.objects.filter(
                    internal_code=product_data["internal_code"]
                ).first()
                if existing:
                    products_by_code[product_data["internal_code"]] = existing
                    self.stdout.write(
                        f"Exists product: {existing.internal_code} — {existing.description}"
                    )
                    continue

                product = create_product(
                    user=product_user,
                    description=product_data["description"],
                    stock=product_data["stock"],
                    price=Decimal(product_data["price"]),
                    internal_code=product_data["internal_code"],
                    reason="seed_dev_data",
                )
                products_by_code[product_data["internal_code"]] = product
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created product: {product.internal_code} — {product.description}"
                    )
                )

            suppliers_by_name = {}
            for supplier_data in SUPPLIERS:
                existing = Supplier.objects.filter(name=supplier_data["name"]).first()
                if existing:
                    suppliers_by_name[supplier_data["name"]] = existing
                    self.stdout.write(f"Exists supplier: {existing.name}")
                    continue

                supplier = create_supplier(
                    name=supplier_data["name"],
                    contact_name=supplier_data.get("contact_name", ""),
                    email=supplier_data.get("email", ""),
                    phone=supplier_data.get("phone", ""),
                )
                suppliers_by_name[supplier_data["name"]] = supplier
                self.stdout.write(
                    self.style.SUCCESS(f"Created supplier: {supplier.name}")
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
                self.stdout.write(
                    f"Linked product {product.internal_code} -> supplier {supplier.name}"
                )

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Dev login credentials (same password for all):"))
        self.stdout.write(f"  Password: {password}")
        self.stdout.write("")
        self.stdout.write("Branch catalogue login (phone UI at /):")
        for email, branch_name in BRANCH_USERS:
            self.stdout.write(f"  {email}  ->  {branch_name}")
        if warehouse_user:
            self.stdout.write("")
            self.stdout.write("Warehouse catalogue management (/admin/products/product/):")
            self.stdout.write(f"  {warehouse_user.email}")
        self.stdout.write("")
        self.stdout.write(
            "Note: branch admin role controls future order permissions per branch. "
            "Catalogue add/edit is warehouse staff only (is_staff), not branch role."
        )
