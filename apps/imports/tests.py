from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.catalog.models import Brand, Product, ProductType
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
        self.parser_myesa = SupplierInvoiceParser.objects.create(
            supplier=self.supplier_a,
            parser_key="myesa",
            version=1,
            is_active=True,
        )

        self.product = Product.objects.create(sku="SKU-BASE", name="Base", default_price=Decimal("100"))
        self.brand_ls2 = Brand.objects.create(name="LS2")
        self.brand_promoto = Brand.objects.create(name="PROMOTO")
        self.type_guantes = ProductType.objects.create(name="GUANTES")
        self.type_candados = ProductType.objects.create(name="CANDADOS")

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
            {"qty": "2.00", "brand_name": "LS2", "product_type_name": "GUANTES"},
            format="json",
        )
        self.assertEqual(edit_line.status_code, 200)

        second_line_id = parsed.data["lines"][1]["id"]
        edit_second_line = self.client.patch(
            f"/api/v1/import-lines/{second_line_id}/",
            {"brand_name": "PROMOTO", "product_type_name": "CANDADOS"},
            format="json",
        )
        self.assertEqual(edit_second_line.status_code, 200)

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
        self.assertEqual(new_product.default_price, Decimal("120.64"))

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
        parsed = self.client.post(f"/api/v1/import-batches/{batch_id}/parse/", {}, format="json")
        line_id = parsed.data["lines"][0]["id"]
        self.client.patch(
            f"/api/v1/import-lines/{line_id}/",
            {"brand_name": "LS2", "product_type_name": "GUANTES"},
            format="json",
        )

        confirm = self.client.post(f"/api/v1/import-batches/{batch_id}/confirm/", {}, format="json")
        self.assertEqual(confirm.status_code, 400)
        self.assertEqual(confirm.data["code"], "subtotal_mismatch")

    def test_suppliers_and_parsers_endpoints(self):
        suppliers_response = self.client.get("/api/v1/suppliers/")
        self.assertEqual(suppliers_response.status_code, 200)
        self.assertGreaterEqual(suppliers_response.data["count"], 2)

        parsers_response = self.client.get(f"/api/v1/supplier-parsers/?supplier={self.supplier_a.id}")
        self.assertEqual(parsers_response.status_code, 200)
        parser_keys = [row["parser_key"] for row in parsers_response.data["results"]]
        self.assertIn("myesa", parser_keys)
        self.assertIn("pipe", parser_keys)
        self.assertNotIn("csv", parser_keys)

    def test_brands_and_product_types_endpoints(self):
        brands_response = self.client.get("/api/v1/brands/")
        self.assertEqual(brands_response.status_code, 200)
        brand_names = [row["name"] for row in brands_response.data["results"]]
        self.assertIn("LS2", brand_names)

        created_brand = self.client.post("/api/v1/brands/", {"name": "AGV"}, format="json")
        self.assertEqual(created_brand.status_code, 201)
        self.assertEqual(created_brand.data["name"], "AGV")

        types_response = self.client.get("/api/v1/product-types/")
        self.assertEqual(types_response.status_code, 200)
        type_names = [row["name"] for row in types_response.data["results"]]
        self.assertIn("GUANTES", type_names)

    def test_parse_myesa_and_set_default_public_price(self):
        raw_text = """
** 5124-1037 5 H87 CANDADO DISCO FRENO PROMOTO CON ALARMA CDA1 CROMO
CLAVE PRODUCTO: 39121903 CLAVE PEDIMENTO: 25 16 1767 5003538
195.80 978.98
** 7101-2461 1 H87 CASCO ABATIBLE LS2 ADVANT X C FUTURE XXL BCO/AZL FF901
CLAVE PRODUCTO: 46181705 CLAVE PEDIMENTO: 25 16 1767 5003910
6,509.97 6,509.97
"""
        batch = self.client.post(
            "/api/v1/import-batches/",
            {
                "supplier": str(self.supplier_a.id),
                "parser": str(self.parser_myesa.id),
                "raw_text": raw_text,
                "subtotal": "7488.95",
                "tax": "1198.23",
                "total": "8687.18",
            },
            format="json",
        )
        self.assertEqual(batch.status_code, 201)

        batch_id = batch.data["id"]
        parsed = self.client.post(f"/api/v1/import-batches/{batch_id}/parse/", {}, format="json")
        self.assertEqual(parsed.status_code, 200)
        self.assertEqual(len(parsed.data["lines"]), 2)

        line = parsed.data["lines"][0]
        self.assertEqual(line["sku"], "5124-1037")
        self.assertEqual(line["qty"], "5.00")
        self.assertEqual(line["unit_cost"], "195.80")
        self.assertEqual(line["unit_price"], "227.13")
        self.assertEqual(line["public_price"], "295.27")

    def test_preview_confirm_from_client_payload(self):
        response = self.client.post(
            "/api/v1/import-batches/preview-confirm/",
            {
                "supplier": str(self.supplier_a.id),
                "parser": str(self.parser_myesa.id),
                "invoice_number": "FAC-1001",
                "invoice_date": "2026-02-27",
                "subtotal": "979.00",
                "tax": "156.64",
                "total": "1135.64",
                "raw_text": "MYESA RAW TEXT",
                "lines": [
                    {
                        "sku": " 5124-1037 ",
                        "name": "CANDADO DISCO FRENO PROMOTO CON ALARMA CDA1 CROMO",
                        "qty": "5.00",
                        "unit_cost": "195.80",
                        "unit_price": "227.13",
                        "public_price": "295.27",
                        "brand_name": "PROMOTO",
                        "product_type_name": "CANDADOS",
                        "is_selected": True,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("batch_id", response.data)
        self.assertIn("purchase_receipt_id", response.data)

        new_product = Product.objects.get(sku="5124-1037")
        self.assertEqual(new_product.default_price, Decimal("295.27"))
        self.assertEqual(self.stock(new_product.id), Decimal("5.00"))
        self.assertEqual(new_product.brand_id, self.brand_promoto.id)
        self.assertEqual(new_product.product_type_id, self.type_candados.id)

    def test_preview_confirm_updates_existing_product_prices(self):
        existing = Product.objects.create(
            sku="5124-1037",
            name="CANDADO EXISTENTE",
            default_price=Decimal("250.00"),
            cost_price=Decimal("150.00"),
        )

        response = self.client.post(
            "/api/v1/import-batches/preview-confirm/",
            {
                "supplier": str(self.supplier_a.id),
                "parser": str(self.parser_myesa.id),
                "invoice_number": "FAC-1002",
                "invoice_date": "2026-02-28",
                "subtotal": "195.80",
                "tax": "31.33",
                "total": "227.13",
                "raw_text": "RAW",
                "lines": [
                    {
                        "sku": "5124-1037",
                        "name": "CANDADO EXISTENTE",
                        "qty": "1.00",
                        "unit_cost": "195.80",
                        "unit_price": "227.13",
                        "public_price": "295.27",
                        "brand_name": "PROMOTO",
                        "product_type_name": "CANDADOS",
                        "is_selected": True,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)

        existing.refresh_from_db()
        self.assertEqual(existing.cost_price, Decimal("195.80"))
        self.assertEqual(existing.default_price, Decimal("295.27"))

    def test_preview_confirm_subtotal_mismatch(self):
        response = self.client.post(
            "/api/v1/import-batches/preview-confirm/",
            {
                "supplier": str(self.supplier_a.id),
                "parser": str(self.parser_myesa.id),
                "subtotal": "100.00",
                "tax": "16.00",
                "total": "116.00",
                "raw_text": "MYESA RAW TEXT",
                "lines": [
                    {
                        "sku": "5124-1037",
                        "name": "CANDADO",
                        "qty": "5.00",
                        "unit_cost": "195.80",
                        "unit_price": "227.13",
                        "public_price": "295.27",
                        "brand_name": "PROMOTO",
                        "product_type_name": "CANDADOS",
                        "is_selected": True,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "subtotal_mismatch")

    def test_preview_confirm_requires_brand_and_product_type(self):
        response = self.client.post(
            "/api/v1/import-batches/preview-confirm/",
            {
                "supplier": str(self.supplier_a.id),
                "parser": str(self.parser_myesa.id),
                "subtotal": "195.80",
                "tax": "31.33",
                "total": "227.13",
                "raw_text": "RAW",
                "lines": [
                    {
                        "sku": "5124-1037",
                        "name": "CANDADO",
                        "qty": "1.00",
                        "unit_cost": "195.80",
                        "unit_price": "227.13",
                        "public_price": "295.27",
                        "is_selected": True,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_lines")

    def test_preview_confirm_rejects_unknown_taxonomy(self):
        response = self.client.post(
            "/api/v1/import-batches/preview-confirm/",
            {
                "supplier": str(self.supplier_a.id),
                "parser": str(self.parser_myesa.id),
                "subtotal": "195.80",
                "tax": "31.33",
                "total": "227.13",
                "raw_text": "RAW",
                "lines": [
                    {
                        "sku": "5124-1037",
                        "name": "CANDADO",
                        "qty": "1.00",
                        "unit_cost": "195.80",
                        "unit_price": "227.13",
                        "public_price": "295.27",
                        "brand_name": "NO_EXISTE",
                        "product_type_name": "CANDADOS",
                        "is_selected": True,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "taxonomy_not_found")
