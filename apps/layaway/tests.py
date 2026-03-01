from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.catalog.models import Product
from apps.inventory.models import InventoryMovement
from apps.layaway.models import Customer, CustomerCredit, Layaway
from apps.investors.models import Investor, InvestorAssignment
from apps.ledger.models import LedgerEntry

User = get_user_model()


class LayawayFlowTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_lay", password="admin123", role="ADMIN")
        self.cashier = User.objects.create_user(username="cashier_lay", password="cashier123", role="CASHIER")
        self.investor_user = User.objects.create_user(username="investor_lay", password="investor123", role="INVESTOR")
        self.investor = Investor.objects.create(user=self.investor_user, display_name="Inversionista QA")
        self.product = Product.objects.create(sku="LAY-001", name="Guantes", default_price=Decimal("300.00"))
        self.product_2 = Product.objects.create(sku="LAY-002", name="Casco", default_price=Decimal("500.00"))
        for product, ref in ((self.product, "layaway-seed-1"), (self.product_2, "layaway-seed-2")):
            InventoryMovement.objects.create(
                product=product,
                movement_type="INBOUND",
                quantity_delta=Decimal("10.00"),
                reference_type="seed",
                reference_id=ref,
                note="seed",
                created_by=self.admin,
            )

    def auth_as(self, username, password):
        token = self.client.post(
            "/api/v1/auth/token/",
            {"username": username, "password": password},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def stock(self, product):
        return InventoryMovement.objects.filter(product=product).aggregate(total=Sum("quantity_delta"))["total"]

    def create_layaway(self, customer_name="Pedro", customer_phone="5551234"):
        self.auth_as("cashier_lay", "cashier123")
        response = self.client.post(
            "/api/v1/layaways/",
            {
                "customer": {"name": customer_name, "phone": customer_phone},
                "lines": [
                    {
                        "product": str(self.product.id),
                        "qty": "1.00",
                        "unit_price": "300.00",
                        "unit_cost": "120.00",
                        "discount_pct": "0.00",
                    },
                    {
                        "product": str(self.product_2.id),
                        "qty": "1.00",
                        "unit_price": "500.00",
                        "unit_cost": "220.00",
                        "discount_pct": "0.00",
                    },
                ],
                "deposit_payments": [{"method": "CASH", "amount": "200.00"}],
                "expires_at": (timezone.now() + timedelta(days=15)).isoformat(),
                "notes": "Cliente frecuente",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        return response

    def test_create_layaway_reserves_stock_and_creates_customer(self):
        response = self.create_layaway()
        self.assertEqual(self.stock(self.product), Decimal("9.00"))
        self.assertEqual(self.stock(self.product_2), Decimal("9.00"))
        layaway = Layaway.objects.get(id=response.data["id"])
        self.assertEqual(layaway.total, Decimal("800.00"))
        self.assertEqual(layaway.amount_paid, Decimal("200.00"))
        self.assertTrue(Customer.objects.filter(phone_normalized="5551234").exists())

    def test_payments_can_use_customer_credit_and_settle(self):
        response = self.create_layaway(customer_name="Luis", customer_phone="222")
        customer = Customer.objects.get(phone_normalized="222")
        CustomerCredit.objects.create(customer=customer, customer_name=customer.name, customer_phone=customer.phone, balance=Decimal("150.00"))

        settle = self.client.post(
            f"/api/v1/layaways/{response.data['id']}/settle/",
            {
                "payments": [
                    {"method": "CUSTOMER_CREDIT", "amount": "150.00"},
                    {"method": "CASH", "amount": "450.00"},
                ]
            },
            format="json",
        )
        self.assertEqual(settle.status_code, 200)
        layaway = Layaway.objects.get(id=response.data["id"])
        self.assertEqual(layaway.status, "SETTLED")
        self.assertEqual(layaway.amount_paid, Decimal("800.00"))
        credit = CustomerCredit.objects.get(customer=customer)
        self.assertEqual(credit.balance, Decimal("0.00"))

    def test_extend_updates_expiration(self):
        response = self.create_layaway(customer_name="Ana", customer_phone="111")
        layaway = Layaway.objects.get(id=response.data["id"])
        new_expiration = timezone.now() + timedelta(days=30)

        extend = self.client.post(
            f"/api/v1/layaways/{layaway.id}/extend/",
            {"new_expires_at": new_expiration.isoformat(), "reason": "Cliente aviso"},
            format="json",
        )
        self.assertEqual(extend.status_code, 200)
        layaway.refresh_from_db()
        self.assertGreaterEqual(layaway.expires_at.date(), new_expiration.date())

    def test_expire_releases_stock_and_creates_credit_for_total_paid(self):
        response = self.create_layaway(customer_name="Maria", customer_phone="444")
        layaway = Layaway.objects.get(id=response.data["id"])
        self.client.post(
            f"/api/v1/layaways/{layaway.id}/payments/",
            {"payments": [{"method": "CASH", "amount": "100.00"}]},
            format="json",
        )
        layaway.refresh_from_db()
        layaway.expires_at = timezone.now() - timedelta(minutes=1)
        layaway.save(update_fields=["expires_at"])

        expire = self.client.post(f"/api/v1/layaways/{layaway.id}/expire/", {}, format="json")
        self.assertEqual(expire.status_code, 200)
        self.assertEqual(self.stock(self.product), Decimal("10.00"))
        self.assertEqual(self.stock(self.product_2), Decimal("10.00"))

        customer = Customer.objects.get(phone_normalized="444")
        credit = CustomerCredit.objects.get(customer=customer)
        self.assertEqual(credit.balance, Decimal("300.00"))

    def test_customer_credit_apply_endpoint(self):
        self.auth_as("cashier_lay", "cashier123")
        customer = Customer.objects.create(phone="999", name="Eva")
        credit = CustomerCredit.objects.create(customer=customer, customer_name="Eva", customer_phone="999", balance=Decimal("100.00"))

        response = self.client.post(
            f"/api/v1/customer-credits/{credit.id}/apply/",
            {"amount": "40.00", "reference_type": "sale", "reference_id": "S-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        credit.refresh_from_db()
        self.assertEqual(credit.balance, Decimal("60.00"))

    def test_settle_layaway_updates_investor_assignment_and_ledger(self):
        InvestorAssignment.objects.create(
            investor=self.investor,
            product=self.product,
            qty_assigned=Decimal("2.00"),
            unit_cost=Decimal("120.00"),
        )
        response = self.create_layaway(customer_name="Leo", customer_phone="777")
        layaway = Layaway.objects.get(id=response.data["id"])

        settle = self.client.post(
            f"/api/v1/layaways/{layaway.id}/settle/",
            {"payments": [{"method": "CASH", "amount": "600.00"}]},
            format="json",
        )
        self.assertEqual(settle.status_code, 200)
        layaway.refresh_from_db()

        assignment = InvestorAssignment.objects.get(investor=self.investor, product=self.product)
        self.assertEqual(assignment.qty_sold, Decimal("1.00"))
        self.assertTrue(LedgerEntry.objects.filter(reference_type="sale", reference_id=str(layaway.settled_sale_id)).exists())

    def test_void_sale_created_from_layaway_reverts_investor_assignment_and_ledger(self):
        InvestorAssignment.objects.create(
            investor=self.investor,
            product=self.product,
            qty_assigned=Decimal("2.00"),
            unit_cost=Decimal("120.00"),
        )
        response = self.create_layaway(customer_name="Lia", customer_phone="888")
        layaway = Layaway.objects.get(id=response.data["id"])

        settle = self.client.post(
            f"/api/v1/layaways/{layaway.id}/settle/",
            {"payments": [{"method": "CASH", "amount": "600.00"}]},
            format="json",
        )
        self.assertEqual(settle.status_code, 200)
        layaway.refresh_from_db()

        sale_id = str(layaway.settled_sale_id)
        void = self.client.post(f"/api/v1/sales/{sale_id}/void/", {"reason": "qa-layaway-void"}, format="json")
        self.assertEqual(void.status_code, 200)

        layaway.refresh_from_db()
        assignment = InvestorAssignment.objects.get(investor=self.investor, product=self.product)
        self.assertEqual(assignment.qty_sold, Decimal("0.00"))
        self.assertEqual(layaway.status, "REFUNDED")
        self.assertTrue(LedgerEntry.objects.filter(reference_type="sale_void", reference_id=sale_id).exists())
