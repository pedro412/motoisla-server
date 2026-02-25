from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.catalog.models import Product
from apps.inventory.models import InventoryMovement
from apps.suppliers.models import Supplier, SupplierInvoiceParser

User = get_user_model()


class ImportFlowTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_import", password="admin123", role="ADMIN")
        self.client.credentials()
        token = self.client.post(
            "/api/v1/auth/token/",
            {"username": "admin_import", "password": "admin123"},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        self.supplier_a = Supplier.objects.create(code="SUPA", name="Supplier A")
        self.supplier_b = Supplier.objects.create(code="SUPB", name="Supplier B")
        self.parser_pipe = SupplierInvoiceParser.objects.create(
            supplier=self.supplier_a,
            parser_key="pipe",
            version=1,
            is_active=True,
        )
        self.parser_csv = SupplierInvoiceParser.objects.create(
            supplier=self.supplier_b,
            parser_key="csv",
            version=1,
            is_active=True,
        )

        self.product = Product.objects.create(sku="SKU-BASE", name="Base", default_price=Decimal("100"))

    def stock(self, product_id):
        return InventoryMovement.objects.filter(product_id=product_id).aggregate(total=Sum("quantity_delta"))["total"]

    def test_create_batch_rejects_parser_from_other_supplier(self):
        response = self.client.post(
            "/api/v1/import-batches/",
            {
                "supplier": str(self.supplier_a.id),
                "parser": str(self.parser_csv.id),
                "raw_text": "SKU-1,Item,1,10,20",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_parse_pipe_parser_and_edit_line_then_confirm(self):
        batch = self.client.post(
            "/api/v1/import-batches/",
            {
                "supplier": str(self.supplier_a.id),
                "parser": str(self.parser_pipe.id),
                "raw_text": "SKU-BASE|Base|1|50|100\\nSKU-NUEVO|Nuevo|1|80|150",
                "subtotal": "130.00",
            },
            format="json",
        )
        self.assertEqual(batch.status_code, 201)

        batch_id = batch.data["id"]
        parsed = self.client.post(f"/api/v1/import-batches/{batch_id}/parse/", {}, format="json")
        self.assertEqual(parsed.status_code, 200)
        self.assertEqual(len(parsed.data["lines"]), 2)

        first_line_id = parsed.data["lines"][0]["id"]
        edit_line = self.client.patch(
            f"/api/v1/import-lines/{first_line_id}/",
            {"qty": "2.00"},
            format="json",
        )
        self.assertEqual(edit_line.status_code, 200)

        update_batch = self.client.patch(
            f"/api/v1/import-batches/{batch_id}/",
            {"subtotal": "180.00"},
            format="json",
        )
        self.assertEqual(update_batch.status_code, 200)

        confirm = self.client.post(f"/api/v1/import-batches/{batch_id}/confirm/", {}, format="json")
        self.assertEqual(confirm.status_code, 201)

        self.assertEqual(self.stock(self.product.id), Decimal("2.00"))
        new_product = Product.objects.get(sku="SKU-NUEVO")
        self.assertEqual(self.stock(new_product.id), Decimal("1.00"))

    def test_confirm_requires_parsed_status(self):
        batch = self.client.post(
            "/api/v1/import-batches/",
            {
                "supplier": str(self.supplier_a.id),
                "parser": str(self.parser_pipe.id),
                "raw_text": "SKU-1|Item|1|10|20",
            },
            format="json",
        )
        batch_id = batch.data["id"]

        confirm = self.client.post(f"/api/v1/import-batches/{batch_id}/confirm/", {}, format="json")
        self.assertEqual(confirm.status_code, 400)

    def test_confirm_rejects_subtotal_mismatch(self):
        batch = self.client.post(
            "/api/v1/import-batches/",
            {
                "supplier": str(self.supplier_a.id),
                "parser": str(self.parser_pipe.id),
                "raw_text": "SKU-BASE|Base|1|50|100",
                "subtotal": "999.00",
            },
            format="json",
        )
        batch_id = batch.data["id"]
        self.client.post(f"/api/v1/import-batches/{batch_id}/parse/", {}, format="json")

        confirm = self.client.post(f"/api/v1/import-batches/{batch_id}/confirm/", {}, format="json")
        self.assertEqual(confirm.status_code, 400)
        self.assertEqual(confirm.data["code"], "subtotal_mismatch")
