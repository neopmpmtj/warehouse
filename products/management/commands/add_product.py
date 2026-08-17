from django.core.management.base import BaseCommand

from products.services import create_product


class Command(BaseCommand):
    help = "Add a new product"

    def add_arguments(self, parser):
        parser.add_argument("description", type=str)
        parser.add_argument("stock", type=str)
        parser.add_argument("price", type=str)

    def handle(self, *args, **options):
        product = create_product(
            description=options["description"],
            stock=options["stock"],
            price=options["price"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Product created: ID={product.id}, {product.description}"
            )
        )