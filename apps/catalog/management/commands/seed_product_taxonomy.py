from django.core.management.base import BaseCommand

from apps.catalog.models import Brand, ProductType


class Command(BaseCommand):
    help = "Seed base product taxonomy (brands and product types)."

    def handle(self, *args, **options):
        brands = ["LS2", "PROMOTO"]
        product_types = ["GUANTES", "CANDADOS", "CHAMARRAS", "CASCOS ABATIBLES"]

        created_brands = 0
        for name in brands:
            _, created = Brand.objects.get_or_create(name=name)
            if created:
                created_brands += 1

        created_types = 0
        for name in product_types:
            _, created = ProductType.objects.get_or_create(name=name)
            if created:
                created_types += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed taxonomy completed. brands_created={created_brands} product_types_created={created_types}"
            )
        )
