from django.core.management.base import BaseCommand, CommandError

from products.models import Product, ProductFamily, StockMovement
from products.services import (
    apply_stock_change,
    create_product,
    get_product_families,
    reactivate_product,
)


class Command(BaseCommand):
    help = "Add a new product (dev/bootstrap; audit user is null)"

    def add_arguments(self, parser):
        parser.add_argument("description", type=str)
        parser.add_argument("price", type=str)
        parser.add_argument(
            "--family",
            required=True,
            help="Product family name (must exist)",
        )
        parser.add_argument(
            "--stock",
            default="0",
            help="Initial stock (applied via stock ledger; default: 0)",
        )
        parser.add_argument(
            "--cost",
            default="0",
            help="Unit cost (default: 0)",
        )
        parser.add_argument(
            "--wholesale",
            default="0",
            help="Wholesale price (default: 0)",
        )
        parser.add_argument(
            "--unit",
            default=Product.UnitOfMeasure.PIECE,
            choices=[choice[0] for choice in Product.UnitOfMeasure.choices],
            help="Unit of measure (default: piece)",
        )
        parser.add_argument(
            "--internal-code",
            dest="internal_code",
            default="",
            help="Optional warehouse internal code",
        )
        parser.add_argument(
            "--reorder-level",
            dest="reorder_level",
            default="0",
            help="Reorder minimum stock threshold (default: 0)",
        )
        parser.add_argument(
            "--activate",
            action="store_true",
            help="Activate in the branch catalogue after create (reason: Genesis)",
        )

    def handle(self, *args, **options):
        family_name = options["family"].strip()
        family = ProductFamily.objects.filter(name=family_name).first()
        if family is None:
            available = ", ".join(
                get_product_families(active_only=False).values_list("name", flat=True)
            )
            raise CommandError(
                f"Product family '{family_name}' not found. Available: {available}"
            )

        product = create_product(
            user=None,
            family=family,
            description=options["description"],
            price=options["price"],
            cost=options["cost"],
            wholesale=options["wholesale"],
            unit_of_measure=options["unit"],
            internal_code=options["internal_code"],
            reorder_level=options["reorder_level"],
        )

        stock = options["stock"]
        if stock and stock != "0":
            apply_stock_change(
                user=None,
                product=product,
                quantity_delta=stock,
                reason="add_product initial stock",
                source_type=StockMovement.SourceType.ADJUSTMENT,
            )
            product.refresh_from_db()

        if options["activate"]:
            reactivate_product(user=None, product=product, reason="Genesis")
            product.refresh_from_db()

        status = "active" if product.is_active else "inactive"
        self.stdout.write(
            self.style.SUCCESS(
                f"Product created ({status}): ID={product.id}, "
                f"{product.internal_code} — {product.description}, stock={product.stock}"
            )
        )
