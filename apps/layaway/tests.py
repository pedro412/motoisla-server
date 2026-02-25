from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.catalog.models import Product
from apps.inventory.models import InventoryMovement
from apps.layaway.models import CustomerCredit, Layaway, LayawayPayment

User = get_user_model()


class LayawayFlowTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_lay", password="admin123", role="ADMIN")
        self.cashier = User.objects.create_user(username="cashier_lay", password="cashier123", role="CASHIER")
        self.product = Product.objects.create(sku="LAY-001", name="Guantes", default_price=Decimal("300.00"))
        InventoryMovement.objects.create(
            product=self.product,
            movement_type="INBOUND",
            quantity_delta=Decimal("10.00"),
            reference_type="seed",
            reference_id="layaway-seed-1",
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

    def stock(self):
        return InventoryMovement.objects.filter(product=self.product).aggregate(total=Sum("quantity_delta"))["total"]

    def test_create_layaway_reserves_stock(self):
        self.auth_as("cashier_lay", "cashier123")
        response = self.client.post(
            "/api/v1/layaways/",
            {
                "product": str(self.product.id),
                "qty": "2.00",
                "customer_name": "Pedro",
                "customer_phone": "555",
                "total_price": "600.00",
                "deposit_amount": "200.00",
                "expires_at": (timezone.now() + timedelta(days=15)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.stock(), Decimal("8.00"))

    def test_settle_requires_exact_remaining_amount(self):
        self.auth_as("cashier_lay", "cashier123")
        create = self.client.post(
            "/api/v1/layaways/",
            {
                "product": str(self.product.id),
                "qty": "1.00",
                "customer_name": "Ana",
                "customer_phone": "111",
                "total_price": "300.00",
                "deposit_amount": "100.00",
                "expires_at": (timezone.now() + timedelta(days=15)).isoformat(),
            },
            format="json",
        )
        layaway_id = create.data["id"]

        bad = self.client.post(f"/api/v1/layaways/{layaway_id}/settle/", {"amount": "150.00"}, format="json")
        self.assertEqual(bad.status_code, 400)

        ok = self.client.post(f"/api/v1/layaways/{layaway_id}/settle/", {"amount": "200.00"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(Layaway.objects.get(id=layaway_id).status, "SETTLED")

    def test_settle_can_apply_customer_credit(self):
        self.auth_as("cashier_lay", "cashier123")
        CustomerCredit.objects.create(customer_name="Luis", customer_phone="222", balance=Decimal("80.00"))

        create = self.client.post(
            "/api/v1/layaways/",
            {
                "product": str(self.product.id),
                "qty": "1.00",
                "customer_name": "Luis",
                "customer_phone": "222",
                "total_price": "300.00",
                "deposit_amount": "100.00",
                "expires_at": (timezone.now() + timedelta(days=15)).isoformat(),
            },
            format="json",
        )
        layaway_id = create.data["id"]

        settle = self.client.post(
            f"/api/v1/layaways/{layaway_id}/settle/",
            {"amount": "120.00", "credit_amount": "80.00"},
            format="json",
        )
        self.assertEqual(settle.status_code, 200)
        credit = CustomerCredit.objects.get(customer_name="Luis", customer_phone="222")
        self.assertEqual(credit.balance, Decimal("0.00"))

    def test_expire_requires_due_or_admin_force(self):
        self.auth_as("cashier_lay", "cashier123")
        create = self.client.post(
            "/api/v1/layaways/",
            {
                "product": str(self.product.id),
                "qty": "1.00",
                "customer_name": "Sofia",
                "customer_phone": "333",
                "total_price": "300.00",
                "deposit_amount": "100.00",
                "expires_at": (timezone.now() + timedelta(days=3)).isoformat(),
            },
            format="json",
        )
        layaway_id = create.data["id"]

        early = self.client.post(f"/api/v1/layaways/{layaway_id}/expire/", {}, format="json")
        self.assertEqual(early.status_code, 400)

        self.auth_as("admin_lay", "admin123")
        forced = self.client.post(f"/api/v1/layaways/{layaway_id}/expire/", {"force": True}, format="json")
        self.assertEqual(forced.status_code, 200)

    def test_expire_releases_stock_and_creates_credit(self):
        self.auth_as("cashier_lay", "cashier123")
        create = self.client.post(
            "/api/v1/layaways/",
            {
                "product": str(self.product.id),
                "qty": "2.00",
                "customer_name": "Maria",
                "customer_phone": "444",
                "total_price": "600.00",
                "deposit_amount": "150.00",
                "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        layaway_id = create.data["id"]
        layaway = Layaway.objects.get(id=layaway_id)
        layaway.expires_at = timezone.now() - timedelta(minutes=1)
        layaway.save(update_fields=["expires_at"])

        expire = self.client.post(f"/api/v1/layaways/{layaway_id}/expire/", {}, format="json")
        self.assertEqual(expire.status_code, 200)
        self.assertEqual(self.stock(), Decimal("10.00"))

        credit = CustomerCredit.objects.get(customer_name="Maria", customer_phone="444")
        self.assertEqual(credit.balance, Decimal("150.00"))

    def test_customer_credit_apply_endpoint(self):
        self.auth_as("cashier_lay", "cashier123")
        credit = CustomerCredit.objects.create(customer_name="Eva", customer_phone="999", balance=Decimal("100.00"))

        response = self.client.post(
            f"/api/v1/customer-credits/{credit.id}/apply/",
            {"amount": "40.00", "reference_type": "sale", "reference_id": "S-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        credit.refresh_from_db()
        self.assertEqual(credit.balance, Decimal("60.00"))
