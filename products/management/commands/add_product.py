from django.core.management.base import BaseCommand, CommandError

from products.models import Product, ProductFamily
from products.services import create_product, get_product_families


class Command(BaseCommand):
    help = "Add a new product (dev/bootstrap; audit user is null)"

    def add_arguments(self, parser):
        parser.add_argument("description", type=str)
        parser.add_argument("stock", type=str)
        parser.add_argument("price", type=str)
        parser.add_argument(
            "--family",
            required=True,
            help="Product family name (must exist)",
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
            stock=options["stock"],
            price=options["price"],
            unit_of_measure=options["unit"],
            internal_code=options["internal_code"],
            reorder_level=options["reorder_level"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Product created: ID={product.id}, {product.internal_code} — {product.description}"
            )
        )
