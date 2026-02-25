from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.catalog.models import Product
from apps.inventory.models import MovementType

User = get_user_model()


class InventoryAuditTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="admin123", role="ADMIN")
        self.product = Product.objects.create(sku="INV-001", name="Casco", default_price=Decimal("100.00"))

    def auth_as_admin(self):
        response = self.client.post(
            "/api/v1/auth/token/",
            {"username": "admin", "password": "admin123"},
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
