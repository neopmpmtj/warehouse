from django.core.management.base import BaseCommand

from products.services import create_product


class Command(BaseCommand):
    help = "Add a new product (dev/bootstrap; audit user is null)"

    def add_arguments(self, parser):
        parser.add_argument("description", type=str)
        parser.add_argument("stock", type=str)
        parser.add_argument("price", type=str)
        parser.add_argument(
            "--internal-code",
            dest="internal_code",
            default="",
            help="Optional warehouse internal code",
        )

    def handle(self, *args, **options):
        product = create_product(
            user=None,
            description=options["description"],
            stock=options["stock"],
            price=options["price"],
            internal_code=options["internal_code"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Product created: ID={product.id}, {product.description}"
            )
        )
