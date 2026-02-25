from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.catalog.models import Product
from apps.inventory.models import InventoryMovement
from apps.investors.models import Investor
from apps.ledger.models import LedgerEntry
from apps.layaway.models import CustomerCredit, Layaway
from apps.sales.models import Sale
from apps.suppliers.models import Supplier, SupplierInvoiceParser

User = get_user_model()


class ApiFlowTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="admin123", role="ADMIN")
        self.cashier = User.objects.create_user(username="cashier", password="cashier123", role="CASHIER")
        self.investor_user = User.objects.create_user(username="investor", password="investor123", role="INVESTOR")
        self.other_investor_user = User.objects.create_user(
            username="investor2", password="investor123", role="INVESTOR"
        )
        self.investor = Investor.objects.create(user=self.investor_user, display_name="Investor One")
        self.other_investor = Investor.objects.create(user=self.other_investor_user, display_name="Investor Two")

        self.product = Product.objects.create(sku="SKU-001", name="Casco", default_price=Decimal("100.00"))

        InventoryMovement.objects.create(
            product=self.product,
            movement_type="INBOUND",
            quantity_delta=Decimal("10"),
            reference_type="seed",
            reference_id="seed-stock",
            note="seed",
            created_by=self.admin,
        )

    def auth(self, username, password):
        response = self.client.post(
            "/api/v1/auth/token/",
            {"username": username, "password": password},
            format="json",
        )
        return response

    def auth_as(self, username, password):
        token = self.auth(username, password).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def stock(self):
        return InventoryMovement.objects.filter(product=self.product).aggregate(total=Sum("quantity_delta"))["total"]

    def test_jwt_login_valid_and_invalid(self):
        ok = self.auth("admin", "admin123")
        self.assertEqual(ok.status_code, 200)
        self.assertIn("access", ok.data)

        bad = self.auth("admin", "wrong")
        self.assertEqual(bad.status_code, 401)

    def test_product_unique_sku_and_search(self):
        self.auth_as("admin", "admin123")
        dup = self.client.post(
            "/api/v1/products/",
            {"sku": "SKU-001", "name": "Duplicado", "default_price": "90.00", "is_active": True},
            format="json",
        )
        self.assertEqual(dup.status_code, 400)

        search = self.client.get("/api/v1/products/?q=cas")
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.data["count"], 1)

    def test_purchase_confirm_increments_stock_and_is_idempotent(self):
        self.auth_as("admin", "admin123")
        supplier = Supplier.objects.create(code="MYESA", name="My Supplier")

        create = self.client.post(
            "/api/v1/purchase-receipts/",
            {
                "supplier": str(supplier.id),
                "invoice_number": "INV-1",
                "lines": [
                    {
                        "product": str(self.product.id),
                        "qty": "5.00",
                        "unit_cost": "50.00",
                        "unit_price": "100.00",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        receipt_id = create.data["id"]

        confirm_1 = self.client.post(f"/api/v1/purchase-receipts/{receipt_id}/confirm/", {}, format="json")
        confirm_2 = self.client.post(f"/api/v1/purchase-receipts/{receipt_id}/confirm/", {}, format="json")

        self.assertEqual(confirm_1.status_code, 200)
        self.assertEqual(confirm_2.status_code, 200)
        self.assertEqual(self.stock(), Decimal("15"))

    def test_sale_confirm_retry_void_window_and_audit(self):
        self.auth_as("cashier", "cashier123")
        sale_resp = self.client.post(
            "/api/v1/sales/",
            {
                "lines": [
                    {
                        "product": str(self.product.id),
                        "qty": "2.00",
                        "unit_price": "100.00",
                        "unit_cost": "40.00",
                        "discount_pct": "5.00",
                    }
                ],
                "payments": [{"method": "CASH", "amount": "190.00"}],
            },
            format="json",
        )
        self.assertEqual(sale_resp.status_code, 201)
        sale_id = sale_resp.data["id"]

        c1 = self.client.post(f"/api/v1/sales/{sale_id}/confirm/", {}, format="json")
        c2 = self.client.post(f"/api/v1/sales/{sale_id}/confirm/", {}, format="json")
        self.assertEqual(c1.status_code, 200)
        self.assertEqual(c2.status_code, 200)
        self.assertEqual(self.stock(), Decimal("8"))

        v = self.client.post(f"/api/v1/sales/{sale_id}/void/", {"reason": "mistake"}, format="json")
        self.assertEqual(v.status_code, 200)
        self.assertEqual(self.stock(), Decimal("10"))
        self.assertTrue(AuditLog.objects.filter(action="sale.void", entity_id=str(sale_id)).exists())

    def test_void_outside_window_rejected_for_cashier(self):
        self.auth_as("cashier", "cashier123")
        sale = Sale.objects.create(cashier=self.cashier, status="CONFIRMED", total=Decimal("100.00"), confirmed_at=timezone.now())
        sale.confirmed_at = timezone.now() - timedelta(minutes=11)
        sale.save(update_fields=["confirmed_at"])

        response = self.client.post(f"/api/v1/sales/{sale.id}/void/", {"reason": "late"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_layaway_expire_creates_customer_credit(self):
        self.auth_as("cashier", "cashier123")
        create = self.client.post(
            "/api/v1/layaways/",
            {
                "product": str(self.product.id),
                "qty": "1.00",
                "customer_name": "Pedro",
                "customer_phone": "555",
                "total_price": "100.00",
                "deposit_amount": "30.00",
                "expires_at": (timezone.now() + timedelta(days=15)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        layaway = Layaway.objects.get(id=create.data["id"])
        layaway.expires_at = timezone.now() - timedelta(minutes=1)
        layaway.save(update_fields=["expires_at"])

        expire = self.client.post(f"/api/v1/layaways/{create.data['id']}/expire/", {}, format="json")
        self.assertEqual(expire.status_code, 200)

        credit = CustomerCredit.objects.get(customer_name="Pedro", customer_phone="555")
        self.assertEqual(credit.balance, Decimal("30.00"))

    def test_investor_can_only_view_own_ledger(self):
        LedgerEntry.objects.create(
            investor=self.investor,
            entry_type="CAPITAL_DEPOSIT",
            capital_delta=Decimal("1000"),
            inventory_delta=Decimal("0"),
            profit_delta=Decimal("0"),
            reference_type="seed",
            reference_id="1",
        )
        LedgerEntry.objects.create(
            investor=self.other_investor,
            entry_type="CAPITAL_DEPOSIT",
            capital_delta=Decimal("2000"),
            inventory_delta=Decimal("0"),
            profit_delta=Decimal("0"),
            reference_type="seed",
            reference_id="2",
        )

        self.auth_as("investor", "investor123")
        me = self.client.get("/api/v1/investors/me/")
        ledger = self.client.get("/api/v1/investors/me/ledger/")

        self.assertEqual(me.status_code, 200)
        self.assertEqual(ledger.status_code, 200)
        self.assertEqual(ledger.data["count"], 1)

    def test_sale_rejects_payment_total_mismatch(self):
        self.auth_as("cashier", "cashier123")
        response = self.client.post(
            "/api/v1/sales/",
            {
                "lines": [
                    {
                        "product": str(self.product.id),
                        "qty": "1.00",
                        "unit_price": "100.00",
                        "unit_cost": "50.00",
                        "discount_pct": "0.00",
                    }
                ],
                "payments": [{"method": "CASH", "amount": "90.00"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("payments", response.data["fields"])

    def test_sale_rejects_card_payment_without_card_type(self):
        self.auth_as("cashier", "cashier123")
        response = self.client.post(
            "/api/v1/sales/",
            {
                "lines": [
                    {
                        "product": str(self.product.id),
                        "qty": "1.00",
                        "unit_price": "100.00",
                        "unit_cost": "50.00",
                        "discount_pct": "0.00",
                    }
                ],
                "payments": [{"method": "CARD", "amount": "100.00"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("card_type", response.data["fields"])

    def test_cashier_discount_above_limit_requires_admin_override(self):
        self.auth_as("cashier", "cashier123")
        response = self.client.post(
            "/api/v1/sales/",
            {
                "lines": [
                    {
                        "product": str(self.product.id),
                        "qty": "1.00",
                        "unit_price": "100.00",
                        "unit_cost": "50.00",
                        "discount_pct": "15.00",
                    }
                ],
                "payments": [{"method": "CASH", "amount": "85.00"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("discount_pct", response.data["fields"])

    def test_cashier_discount_above_limit_with_admin_override_is_allowed(self):
        self.auth_as("cashier", "cashier123")
        response = self.client.post(
            "/api/v1/sales/",
            {
                "lines": [
                    {
                        "product": str(self.product.id),
                        "qty": "1.00",
                        "unit_price": "100.00",
                        "unit_cost": "50.00",
                        "discount_pct": "15.00",
                    }
                ],
                "payments": [{"method": "CASH", "amount": "85.00"}],
                "override_admin_username": "admin",
                "override_admin_password": "admin123",
                "override_reason": "Autorizado por promo",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        sale_id = response.data["id"]
        self.assertTrue(AuditLog.objects.filter(action="sale.discount_override", entity_id=str(sale_id)).exists())

    def test_admin_can_void_outside_window(self):
        sale = Sale.objects.create(cashier=self.cashier, status="CONFIRMED", total=Decimal("100.00"), confirmed_at=timezone.now())
        sale.confirmed_at = timezone.now() - timedelta(minutes=120)
        sale.save(update_fields=["confirmed_at"])

        self.auth_as("admin", "admin123")
        response = self.client.post(f"/api/v1/sales/{sale.id}/void/", {"reason": "Autorizado"}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_import_parse_and_confirm_creates_receipt_and_stock(self):
        self.auth_as("admin", "admin123")
        supplier = Supplier.objects.create(code="EDGE", name="Edge")
        parser = SupplierInvoiceParser.objects.create(
            supplier=supplier,
            parser_key="default",
            version=1,
            description="Default parser",
            is_active=True,
        )

        batch = self.client.post(
            "/api/v1/import-batches/",
            {
                "supplier": str(supplier.id),
                "parser": str(parser.id),
                "raw_text": "SKU-001,Casco,2,40,100\\nSKU-NEW,Llanta,1,80,150",
                "invoice_number": "IMP-1",
            },
            format="json",
        )
        self.assertEqual(batch.status_code, 201)
        batch_id = batch.data["id"]

        parsed = self.client.post(f"/api/v1/import-batches/{batch_id}/parse/", {}, format="json")
        self.assertEqual(parsed.status_code, 200)
        self.assertEqual(len(parsed.data["lines"]), 2)

        confirmed = self.client.post(f"/api/v1/import-batches/{batch_id}/confirm/", {}, format="json")
        self.assertEqual(confirmed.status_code, 201)
        self.assertIn("purchase_receipt_id", confirmed.data)
        self.assertEqual(self.stock(), Decimal("12"))

    def test_import_confirm_rejects_duplicate_selected_sku(self):
        self.auth_as("admin", "admin123")
        supplier = Supplier.objects.create(code="FREE", name="Freedconn")
        parser = SupplierInvoiceParser.objects.create(
            supplier=supplier,
            parser_key="default",
            version=1,
            description="Default parser",
            is_active=True,
        )

        batch = self.client.post(
            "/api/v1/import-batches/",
            {
                "supplier": str(supplier.id),
                "parser": str(parser.id),
                "raw_text": "SKU-DUP,Item A,1,10,20\\nSKU-DUP,Item B,1,10,20",
            },
            format="json",
        )
        batch_id = batch.data["id"]
        self.client.post(f"/api/v1/import-batches/{batch_id}/parse/", {}, format="json")
        confirmed = self.client.post(f"/api/v1/import-batches/{batch_id}/confirm/", {}, format="json")
        self.assertEqual(confirmed.status_code, 400)
