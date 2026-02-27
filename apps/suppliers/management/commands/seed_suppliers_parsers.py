from django.core.management.base import BaseCommand
from django.db import transaction

from apps.suppliers.models import Supplier, SupplierInvoiceParser


class Command(BaseCommand):
    help = "Seed base suppliers and invoice parsers for local development"

    @transaction.atomic
    def handle(self, *args, **options):
        supplier, created_supplier = Supplier.objects.get_or_create(
            code="MYESA",
            defaults={
                "name": "MYESA",
                "is_active": True,
            },
        )

        supplier_updates = []
        if supplier.name != "MYESA":
            supplier.name = "MYESA"
            supplier_updates.append("name")
        if not supplier.is_active:
            supplier.is_active = True
            supplier_updates.append("is_active")
        if supplier_updates:
            supplier.save(update_fields=supplier_updates)

        parser, created_parser = SupplierInvoiceParser.objects.get_or_create(
            supplier=supplier,
            parser_key="myesa",
            defaults={
                "version": 1,
                "description": "Parser MYESA",
                "is_active": True,
            },
        )

        parser_updates = []
        if parser.version != 1:
            parser.version = 1
            parser_updates.append("version")
        if parser.description != "Parser MYESA":
            parser.description = "Parser MYESA"
            parser_updates.append("description")
        if not parser.is_active:
            parser.is_active = True
            parser_updates.append("is_active")
        if parser_updates:
            parser.save(update_fields=parser_updates)

        self.stdout.write(self.style.SUCCESS("Seed completed."))
        self.stdout.write(f"Supplier: {supplier.code} ({'created' if created_supplier else 'existing'})")
        self.stdout.write(
            f"Parser: {parser.parser_key} v{parser.version} ({'created' if created_parser else 'existing'})"
        )
