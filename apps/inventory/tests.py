from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.catalog.models import Product
from apps.inventory.models import InventoryMovement, MovementType

User = get_user_model()


class InventoryAuditTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="admin123", role="ADMIN")
        self.cashier = User.objects.create_user(username="cashier", password="cash123", role="CASHIER")
        self.product = Product.objects.create(sku="INV-001", name="Casco", default_price=Decimal("100.00"))
        self.other_product = Product.objects.create(sku="INV-002", name="Guantes", default_price=Decimal("80.00"))

    def auth_as_admin(self):
        response = self.client.post(
            "/api/v1/auth/token/",
            {"username": "admin", "password": "admin123"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def auth_as_cashier(self):
        response = self.client.post(
            "/api/v1/auth/token/",
            {"username": "cashier", "password": "cash123"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_inventory_adjustment_create_is_audited(self):
        self.auth_as_admin()
        response = self.client.post(
            "/api/v1/inventory/movements/",
            {
                "product": str(self.product.id),
                "movement_type": MovementType.ADJUSTMENT,
                "quantity_delta": "3.00",
                "reference_type": "manual_adjustment",
                "reference_id": "adj-001",
                "note": "Ajuste manual",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        movement_id = response.data["id"]
        self.assertTrue(AuditLog.objects.filter(action="inventory.adjustment.create", entity_id=movement_id).exists())

    def test_inventory_movements_list_can_filter_by_product_and_returns_enriched_fields(self):
        self.auth_as_admin()
        InventoryMovement.objects.create(
            product=self.product,
            movement_type=MovementType.INBOUND,
            quantity_delta=Decimal("5.00"),
            reference_type="purchase_receipt",
            reference_id="rcpt-1",
            note="Compra inicial",
            created_by=self.admin,
        )
        InventoryMovement.objects.create(
            product=self.other_product,
            movement_type=MovementType.INBOUND,
            quantity_delta=Decimal("1.00"),
            reference_type="purchase_receipt",
            reference_id="rcpt-2",
            note="Compra secundaria",
            created_by=self.admin,
        )

        response = self.client.get(f"/api/v1/inventory/movements/?product={self.product.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

        item = response.data["results"][0]
        self.assertEqual(str(item["product"]), str(self.product.id))
        self.assertEqual(item["product_sku"], "INV-001")
        self.assertEqual(item["product_name"], "Casco")
        self.assertEqual(item["created_by_username"], "admin")
        self.assertEqual(item["reference_type"], "purchase_receipt")

    def test_cashier_can_view_inventory_movements(self):
        InventoryMovement.objects.create(
            product=self.product,
            movement_type=MovementType.INBOUND,
            quantity_delta=Decimal("2.00"),
            reference_type="seed",
            reference_id="seed-1",
            note="Seed",
            created_by=self.admin,
        )

        self.auth_as_cashier()
        response = self.client.get(f"/api/v1/inventory/movements/?product={self.product.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_inventory_movements_require_authentication(self):
        response = self.client.get("/api/v1/inventory/movements/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
