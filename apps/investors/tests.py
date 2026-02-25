from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.catalog.models import Product
from apps.investors.models import Investor
from apps.ledger.models import LedgerEntry, LedgerEntryType

User = get_user_model()


class InvestorLedgerTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_inv", password="admin123", role="ADMIN")
        self.cashier = User.objects.create_user(username="cashier_inv", password="cashier123", role="CASHIER")
        self.investor_user = User.objects.create_user(username="investor_inv", password="investor123", role="INVESTOR")

        self.investor = Investor.objects.create(user=self.investor_user, display_name="Investor Uno")
        self.product = Product.objects.create(sku="INV-001", name="Intercom", default_price=Decimal("100.00"))

    def auth_as(self, username, password):
        token = self.client.post(
            "/api/v1/auth/token/",
            {"username": username, "password": password},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_admin_deposit_and_withdraw(self):
        self.auth_as("admin_inv", "admin123")

        deposit = self.client.post(
            f"/api/v1/investors/{self.investor.id}/deposit/",
            {"amount": "500.00", "note": "capital inicial"},
            format="json",
        )
        self.assertEqual(deposit.status_code, 201)

        withdraw = self.client.post(
            f"/api/v1/investors/{self.investor.id}/withdraw/",
            {"amount": "200.00", "note": "retiro parcial"},
            format="json",
        )
        self.assertEqual(withdraw.status_code, 201)

        me = self.client.get("/api/v1/investors/me/")
        self.assertEqual(me.status_code, 404)

        ledger_resp = self.client.get(f"/api/v1/investors/{self.investor.id}/ledger/")
        self.assertEqual(ledger_resp.status_code, 200)
        self.assertEqual(ledger_resp.data["count"], 2)

    def test_withdraw_rejected_when_no_capital(self):
        self.auth_as("admin_inv", "admin123")
        response = self.client.post(
            f"/api/v1/investors/{self.investor.id}/withdraw/",
            {"amount": "1.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_withdrawal")

    def test_reinvest_rejected_without_profit(self):
        self.auth_as("admin_inv", "admin123")
        response = self.client.post(
            f"/api/v1/investors/{self.investor.id}/reinvest/",
            {"amount": "10.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_reinvestment")

    def test_reinvest_moves_profit_to_capital(self):
        LedgerEntry.objects.create(
            investor=self.investor,
            entry_type=LedgerEntryType.PROFIT_SHARE,
            capital_delta=Decimal("0.00"),
            inventory_delta=Decimal("0.00"),
            profit_delta=Decimal("100.00"),
            reference_type="seed",
            reference_id="1",
        )

        self.auth_as("admin_inv", "admin123")
        response = self.client.post(
            f"/api/v1/investors/{self.investor.id}/reinvest/",
            {"amount": "40.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data["balances"]["capital"]), Decimal("40.00"))
        self.assertEqual(Decimal(response.data["balances"]["profit"]), Decimal("60.00"))

    def test_admin_can_create_assignment(self):
        self.auth_as("admin_inv", "admin123")
        response = self.client.post(
            "/api/v1/investors/assignments/",
            {
                "investor": str(self.investor.id),
                "product": str(self.product.id),
                "qty_assigned": "5.00",
                "unit_cost": "50.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Decimal(response.data["qty_assigned"]), Decimal("5.00"))
        assignment_id = response.data["id"]
        self.assertTrue(AuditLog.objects.filter(action="investor.assignment.create", entity_id=assignment_id).exists())

        updated = self.client.patch(
            f"/api/v1/investors/assignments/{assignment_id}/",
            {"qty_assigned": "6.00"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="investor.assignment.update", entity_id=assignment_id).exists())

        deleted = self.client.delete(f"/api/v1/investors/assignments/{assignment_id}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertTrue(AuditLog.objects.filter(action="investor.assignment.delete", entity_id=assignment_id).exists())

    def test_investor_can_only_view_own_profile(self):
        self.auth_as("investor_inv", "investor123")
        me = self.client.get("/api/v1/investors/me/")
        self.assertEqual(me.status_code, 200)

        denied = self.client.get(f"/api/v1/investors/{self.investor.id}/")
        self.assertEqual(denied.status_code, 403)
