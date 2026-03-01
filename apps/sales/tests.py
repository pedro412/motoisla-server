import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.catalog.models import Brand, Product, ProductType
from apps.expenses.models import Expense
from apps.inventory.models import InventoryMovement
from apps.imports.models import InvoiceImportLine
from apps.investors.models import Investor, InvestorAssignment
from apps.ledger.models import LedgerEntry
from apps.ledger.services import current_balances
from apps.layaway.models import CustomerCredit, Layaway
from apps.sales.models import CardCommissionPlan, CardType, Payment, PaymentMethod, Sale, SaleLine, SaleStatus, VoidEvent
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

    def card_plan(self, code):
        return CardCommissionPlan.objects.get(code=code)

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
                "customer": {"name": "Pedro", "phone": "555"},
                "lines": [
                    {
                        "product": str(self.product.id),
                        "qty": "1.00",
                        "unit_price": "100.00",
                        "unit_cost": "40.00",
                        "discount_pct": "0.00",
                    }
                ],
                "deposit_payments": [{"method": "CASH", "amount": "30.00"}],
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

    def test_sale_accepts_card_plan_and_persists_snapshot(self):
        self.auth_as("cashier", "cashier123")
        plan = self.card_plan("MSI_3")

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
                "payments": [{"method": "CARD", "amount": "100.00", "card_plan_id": str(plan.id)}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        payment = Payment.objects.get(sale_id=response.data["id"])
        self.assertEqual(payment.card_commission_plan_id, plan.id)
        self.assertEqual(payment.card_plan_code, "MSI_3")
        self.assertEqual(payment.card_plan_label, "3 MSI")
        self.assertEqual(payment.installments_months, 3)
        self.assertEqual(payment.commission_rate, Decimal("0.0558"))
        self.assertEqual(payment.card_type, CardType.MSI_3)

    def test_sale_legacy_card_type_persists_commission_snapshot(self):
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
                "payments": [{"method": "CARD", "amount": "100.00", "card_type": "NORMAL"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        payment = Payment.objects.get(sale_id=response.data["id"])
        self.assertEqual(payment.card_plan_code, "NORMAL")
        self.assertEqual(payment.card_plan_label, "Tarjeta")
        self.assertEqual(payment.installments_months, 0)
        self.assertEqual(payment.commission_rate, Decimal("0.0200"))
        self.assertEqual(payment.card_type, CardType.NORMAL)

    def test_sale_rejects_inactive_card_plan(self):
        self.auth_as("cashier", "cashier123")
        inactive_plan = CardCommissionPlan.objects.create(
            code=f"CUSTOM_{uuid.uuid4().hex[:8].upper()}",
            label="6 MSI",
            installments_months=6,
            commission_rate=Decimal("0.1000"),
            is_active=False,
            sort_order=20,
        )

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
                "payments": [{"method": "CARD", "amount": "100.00", "card_plan_id": str(inactive_plan.id)}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("payments", response.data["fields"])

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

    def test_card_commission_plan_list_returns_active_plans_only(self):
        CardCommissionPlan.objects.create(
            code="MSI_6",
            label="6 MSI",
            installments_months=6,
            commission_rate=Decimal("0.0800"),
            is_active=False,
            sort_order=20,
        )
        self.auth_as("cashier", "cashier123")

        response = self.client.get("/api/v1/card-commission-plans/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual([item["code"] for item in response.data["results"]], ["NORMAL", "MSI_3"])

    def test_sales_list_includes_history_fields_and_void_rules(self):
        older = Sale.objects.create(
            cashier=self.cashier,
            status=SaleStatus.CONFIRMED,
            total=Decimal("90.00"),
            confirmed_at=timezone.now() - timedelta(minutes=5),
        )
        latest = Sale.objects.create(
            cashier=self.admin,
            status=SaleStatus.CONFIRMED,
            total=Decimal("120.00"),
            confirmed_at=timezone.now() - timedelta(minutes=2),
        )
        voided = Sale.objects.create(
            cashier=self.cashier,
            status=SaleStatus.VOID,
            total=Decimal("70.00"),
            confirmed_at=timezone.now() - timedelta(minutes=1),
            voided_at=timezone.now(),
        )
        Sale.objects.filter(id=older.id).update(created_at=timezone.now() - timedelta(hours=2))
        Sale.objects.filter(id=latest.id).update(created_at=timezone.now())
        Sale.objects.filter(id=voided.id).update(created_at=timezone.now() - timedelta(hours=1))
        VoidEvent.objects.create(sale=voided, reason="Mistake", actor=self.cashier)

        self.auth_as("cashier", "cashier123")
        response = self.client.get("/api/v1/sales/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["id"], str(latest.id))
        results_by_id = {row["id"]: row for row in response.data["results"]}
        self.assertTrue(results_by_id[str(older.id)]["can_void"])
        self.assertFalse(results_by_id[str(latest.id)]["can_void"])
        self.assertEqual(results_by_id[str(voided.id)]["void_reason"], "Mistake")
        self.assertFalse(results_by_id[str(voided.id)]["can_void"])

    def test_sales_list_marks_admin_can_void_confirmed_sales(self):
        sale = Sale.objects.create(
            cashier=self.cashier,
            status=SaleStatus.CONFIRMED,
            total=Decimal("90.00"),
            confirmed_at=timezone.now() - timedelta(minutes=120),
        )

        self.auth_as("admin", "admin123")
        response = self.client.get("/api/v1/sales/")

        self.assertEqual(response.status_code, 200)
        results_by_id = {row["id"]: row for row in response.data["results"]}
        self.assertTrue(results_by_id[str(sale.id)]["can_void"])

    def test_sale_detail_includes_customer_summary_and_line_metadata(self):
        self.auth_as("cashier", "cashier123")
        sale_resp = self.client.post(
            "/api/v1/sales/",
            {
                "customer_phone": "9991234567",
                "customer_name": "Cliente QA",
                "lines": [
                    {
                        "product": str(self.product.id),
                        "qty": "1.00",
                        "unit_price": "100.00",
                        "unit_cost": "50.00",
                        "discount_pct": "0.00",
                    }
                ],
                "payments": [{"method": "CASH", "amount": "100.00"}],
            },
            format="json",
        )
        self.assertEqual(sale_resp.status_code, 201)

        detail = self.client.get(f"/api/v1/sales/{sale_resp.data['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["cashier_username"], "cashier")
        self.assertEqual(detail.data["customer_summary"]["name"], "Cliente QA")
        self.assertEqual(detail.data["customer_summary"]["phone"], "9991234567")
        self.assertEqual(detail.data["customer_summary"]["sales_count"], 1)
        self.assertEqual(detail.data["customer_summary"]["confirmed_sales_count"], 0)
        self.assertEqual(detail.data["lines"][0]["product_sku"], "SKU-001")
        self.assertEqual(detail.data["lines"][0]["product_name"], "Casco")

    def test_sale_update_endpoint_is_not_allowed(self):
        self.auth_as("cashier", "cashier123")
        sale_resp = self.client.post(
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
                "payments": [{"method": "CASH", "amount": "100.00"}],
            },
            format="json",
        )
        self.assertEqual(sale_resp.status_code, 201)
        sale_id = sale_resp.data["id"]
        patch_response = self.client.patch(f"/api/v1/sales/{sale_id}/", {"total": "1.00"}, format="json")
        self.assertEqual(patch_response.status_code, 405)

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

        brand = Brand.objects.create(name="Genérica")
        product_type = ProductType.objects.create(name="Accesorio")
        InvoiceImportLine.objects.filter(batch_id=batch_id).update(
            brand=brand,
            product_type=product_type,
            brand_name=brand.name,
            product_type_name=product_type.name,
        )

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

    def test_metrics_supports_date_range_top_products_and_payment_breakdown(self):
        self.auth_as("admin", "admin123")
        product_2 = Product.objects.create(sku="SKU-002", name="Guantes", default_price=Decimal("150.00"))

        today = timezone.now()
        in_range_day = today - timedelta(days=2)
        out_of_range_day = today - timedelta(days=15)

        sale_1 = Sale.objects.create(
            cashier=self.cashier,
            status=SaleStatus.CONFIRMED,
            subtotal=Decimal("200.00"),
            discount_amount=Decimal("0.00"),
            total=Decimal("200.00"),
            confirmed_at=in_range_day,
        )
        SaleLine.objects.create(
            sale=sale_1,
            product=self.product,
            qty=Decimal("2.00"),
            unit_price=Decimal("100.00"),
            unit_cost=Decimal("40.00"),
            discount_pct=Decimal("0.00"),
        )
        Payment.objects.create(sale=sale_1, method=PaymentMethod.CASH, amount=Decimal("200.00"))

        sale_2 = Sale.objects.create(
            cashier=self.cashier,
            status=SaleStatus.CONFIRMED,
            subtotal=Decimal("100.00"),
            discount_amount=Decimal("5.00"),
            total=Decimal("95.00"),
            confirmed_at=in_range_day,
        )
        SaleLine.objects.create(
            sale=sale_2,
            product=self.product,
            qty=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            unit_cost=Decimal("40.00"),
            discount_pct=Decimal("5.00"),
        )
        Payment.objects.create(
            sale=sale_2,
            method=PaymentMethod.CARD,
            amount=Decimal("95.00"),
            card_type=CardType.NORMAL,
        )

        sale_3 = Sale.objects.create(
            cashier=self.cashier,
            status=SaleStatus.CONFIRMED,
            subtotal=Decimal("150.00"),
            discount_amount=Decimal("0.00"),
            total=Decimal("150.00"),
            confirmed_at=out_of_range_day,
        )
        SaleLine.objects.create(
            sale=sale_3,
            product=product_2,
            qty=Decimal("1.00"),
            unit_price=Decimal("150.00"),
            unit_cost=Decimal("80.00"),
            discount_pct=Decimal("0.00"),
        )
        Payment.objects.create(
            sale=sale_3,
            method=PaymentMethod.CARD,
            amount=Decimal("150.00"),
            card_type=CardType.MSI_3,
        )

        Sale.objects.create(
            cashier=self.cashier,
            status=SaleStatus.DRAFT,
            subtotal=Decimal("500.00"),
            discount_amount=Decimal("0.00"),
            total=Decimal("500.00"),
        )

        response = self.client.get(
            "/api/v1/metrics/",
            {
                "date_from": (today - timedelta(days=7)).date().isoformat(),
                "date_to": today.date().isoformat(),
                "top_limit": 5,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["sales_count"], 2)
        self.assertEqual(Decimal(str(response.data["total_sales"])), Decimal("295.00"))
        self.assertEqual(Decimal(str(response.data["avg_ticket"])), Decimal("147.5"))

        top_products = response.data["top_products"]
        self.assertEqual(len(top_products), 1)
        self.assertEqual(top_products[0]["product__sku"], "SKU-001")
        self.assertEqual(Decimal(str(top_products[0]["units_sold"])), Decimal("3.00"))
        self.assertEqual(Decimal(str(top_products[0]["sales_amount"])), Decimal("295.00"))

        by_method = {row["method"]: row for row in response.data["payment_breakdown"]["by_method"]}
        self.assertEqual(Decimal(str(by_method["CASH"]["total_amount"])), Decimal("200.00"))
        self.assertEqual(by_method["CASH"]["transactions"], 1)
        self.assertEqual(Decimal(str(by_method["CARD"]["total_amount"])), Decimal("95.00"))
        self.assertEqual(by_method["CARD"]["transactions"], 1)

        card_types = {row["card_type"]: row for row in response.data["payment_breakdown"]["card_types"]}
        self.assertIn("NORMAL", card_types)
        self.assertEqual(Decimal(str(card_types["NORMAL"]["total_amount"])), Decimal("95.00"))

    def test_sales_report_includes_daily_and_cashier_breakdown(self):
        self.auth_as("admin", "admin123")
        second_cashier = User.objects.create_user(username="cashier2", password="cashier123", role="CASHIER")
        now = timezone.now()

        Sale.objects.create(
            cashier=self.cashier,
            status=SaleStatus.CONFIRMED,
            subtotal=Decimal("200.00"),
            discount_amount=Decimal("0.00"),
            total=Decimal("200.00"),
            confirmed_at=now - timedelta(days=1),
        )
        Sale.objects.create(
            cashier=second_cashier,
            status=SaleStatus.CONFIRMED,
            subtotal=Decimal("150.00"),
            discount_amount=Decimal("0.00"),
            total=Decimal("150.00"),
            confirmed_at=now,
        )

        response = self.client.get(
            "/api/v1/reports/sales/",
            {
                "date_from": (now - timedelta(days=7)).date().isoformat(),
                "date_to": now.date().isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("sales_by_day", response.data)
        self.assertIn("sales_by_cashier", response.data)
        self.assertEqual(len(response.data["sales_by_day"]), 2)

        cashiers = {row["cashier__username"]: row for row in response.data["sales_by_cashier"]}
        self.assertEqual(Decimal(str(cashiers["cashier"]["total_sales"])), Decimal("200.00"))
        self.assertEqual(cashiers["cashier"]["sales_count"], 1)
        self.assertEqual(Decimal(str(cashiers["cashier2"]["total_sales"])), Decimal("150.00"))
        self.assertEqual(cashiers["cashier2"]["sales_count"], 1)

    def test_sales_report_includes_expenses_summary(self):
        self.auth_as("admin", "admin123")
        now = timezone.now()
        Sale.objects.create(
            cashier=self.cashier,
            status=SaleStatus.CONFIRMED,
            subtotal=Decimal("300.00"),
            discount_amount=Decimal("0.00"),
            total=Decimal("300.00"),
            confirmed_at=now,
        )
        Expense.objects.create(
            category="Rent",
            description="Store rent",
            amount=Decimal("120.00"),
            expense_date=now.date(),
            created_by=self.admin,
        )
        Expense.objects.create(
            category="Utilities",
            description="Electricity",
            amount=Decimal("30.00"),
            expense_date=now.date(),
            created_by=self.admin,
        )
        Expense.objects.create(
            category="Rent",
            description="Old rent",
            amount=Decimal("999.00"),
            expense_date=(now - timedelta(days=45)).date(),
            created_by=self.admin,
        )

        response = self.client.get(
            "/api/v1/reports/sales/",
            {
                "date_from": (now - timedelta(days=7)).date().isoformat(),
                "date_to": now.date().isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("expenses_summary", response.data)
        self.assertEqual(Decimal(str(response.data["expenses_summary"]["total_expenses"])), Decimal("150.00"))
        self.assertEqual(response.data["expenses_summary"]["expenses_count"], 2)
        by_category = {row["category"]: row for row in response.data["expenses_summary"]["by_category"]}
        self.assertEqual(Decimal(str(by_category["Rent"]["total_amount"])), Decimal("120.00"))
        self.assertEqual(Decimal(str(by_category["Utilities"]["total_amount"])), Decimal("30.00"))
        self.assertEqual(Decimal(str(response.data["net_sales_after_expenses"])), Decimal("150.00"))

    def test_investor_sale_confirm_and_void_revert_stock_assignment_and_ledger(self):
        self.auth_as("cashier", "cashier123")
        assignment = InvestorAssignment.objects.create(
            investor=self.investor,
            product=self.product,
            qty_assigned=Decimal("5.00"),
            unit_cost=Decimal("40.00"),
        )

        sale_resp = self.client.post(
            "/api/v1/sales/",
            {
                "lines": [
                    {
                        "product": str(self.product.id),
                        "qty": "2.00",
                        "unit_price": "100.00",
                        "unit_cost": "40.00",
                        "discount_pct": "0.00",
                    }
                ],
                "payments": [{"method": "CASH", "amount": "200.00"}],
            },
            format="json",
        )
        self.assertEqual(sale_resp.status_code, 201)
        sale_id = sale_resp.data["id"]

        confirm = self.client.post(f"/api/v1/sales/{sale_id}/confirm/", {}, format="json")
        self.assertEqual(confirm.status_code, 200)
        assignment.refresh_from_db()
        self.assertEqual(assignment.qty_sold, Decimal("2.00"))
        self.assertEqual(self.stock(), Decimal("8.00"))

        balances_after_confirm = current_balances(self.investor)
        self.assertEqual(Decimal(str(balances_after_confirm["capital"])), Decimal("80.00"))
        self.assertEqual(Decimal(str(balances_after_confirm["inventory"])), Decimal("-80.00"))
        self.assertEqual(Decimal(str(balances_after_confirm["profit"])), Decimal("60.00"))

        void = self.client.post(f"/api/v1/sales/{sale_id}/void/", {"reason": "test-reverse"}, format="json")
        self.assertEqual(void.status_code, 200)
        assignment.refresh_from_db()
        self.assertEqual(assignment.qty_sold, Decimal("0.00"))
        self.assertEqual(self.stock(), Decimal("10.00"))

        balances_after_void = current_balances(self.investor)
        self.assertEqual(Decimal(str(balances_after_void["capital"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(balances_after_void["inventory"])), Decimal("0.00"))
        self.assertEqual(Decimal(str(balances_after_void["profit"])), Decimal("0.00"))
        self.assertTrue(LedgerEntry.objects.filter(reference_type="sale_void", reference_id=str(sale_id)).exists())

    def test_voided_sale_is_excluded_from_metrics(self):
        self.auth_as("cashier", "cashier123")
        sale_resp = self.client.post(
            "/api/v1/sales/",
            {
                "lines": [
                    {
                        "product": str(self.product.id),
                        "qty": "1.00",
                        "unit_price": "100.00",
                        "unit_cost": "40.00",
                        "discount_pct": "0.00",
                    }
                ],
                "payments": [{"method": "CASH", "amount": "100.00"}],
            },
            format="json",
        )
        sale_id = sale_resp.data["id"]
        self.client.post(f"/api/v1/sales/{sale_id}/confirm/", {}, format="json")
        self.client.post(f"/api/v1/sales/{sale_id}/void/", {"reason": "metrics-check"}, format="json")

        self.auth_as("admin", "admin123")
        metrics = self.client.get("/api/v1/metrics/")
        self.assertEqual(metrics.status_code, 200)
        self.assertEqual(metrics.data["sales_count"], 0)
        self.assertEqual(Decimal(str(metrics.data["total_sales"])), Decimal("0.00"))
