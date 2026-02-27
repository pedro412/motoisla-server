from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum
from rest_framework.test import APITestCase

from apps.catalog.models import Product
from apps.inventory.models import InventoryMovement, MovementType
from apps.purchases.models import PurchaseReceipt, PurchaseReceiptLine, ReceiptStatus
from apps.suppliers.models import Supplier

User = get_user_model()


class PurchaseReceiptViewSetTests(APITestCase):
    def setUp(self):
        self.cashier = User.objects.create_user(username="cashier_receipts", password="cash123", role="CASHIER")
        self.other = User.objects.create_user(username="other_receipts", password="cash123", role="CASHIER")
        token = self.client.post(
            "/api/v1/auth/token/",
            {"username": "cashier_receipts", "password": "cash123"},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        self.supplier = Supplier.objects.create(code="SUPR", name="Supplier Receipts")
        self.product = Product.objects.create(sku="SKU-REC", name="Producto Recibo", default_price=Decimal("150.00"))

    def stock(self):
        return InventoryMovement.objects.filter(product=self.product).aggregate(total=Sum("quantity_delta"))["total"]

    def create_posted_receipt(self, *, actor=None, invoice_number="FAC-1"):
        actor = actor or self.cashier
        receipt = PurchaseReceipt.objects.create(
            supplier=self.supplier,
            invoice_number=invoice_number,
            status=ReceiptStatus.POSTED,
            subtotal=Decimal("100.00"),
            tax=Decimal("16.00"),
            total=Decimal("116.00"),
            created_by=actor,
            posted_at=self._now(),
        )
        PurchaseReceiptLine.objects.create(
            receipt=receipt,
            product=self.product,
            qty=Decimal("2.00"),
            unit_cost=Decimal("50.00"),
            unit_price=Decimal("75.00"),
        )
        InventoryMovement.objects.create(
            product=self.product,
            movement_type=MovementType.INBOUND,
            quantity_delta=Decimal("2.00"),
            reference_type="purchase_receipt",
            reference_id=str(receipt.id),
            note="seed receipt",
            created_by=actor,
        )
        return receipt

    def _now(self):
        from django.utils import timezone

        return timezone.now()

    def test_list_returns_only_current_user_receipts(self):
        own = self.create_posted_receipt(invoice_number="FAC-OWN")
        self.create_posted_receipt(actor=self.other, invoice_number="FAC-OTHER")

        response = self.client.get("/api/v1/purchase-receipts/")
        self.assertEqual(response.status_code, 200)
        invoice_numbers = [row["invoice_number"] for row in response.data["results"]]
        self.assertIn(own.invoice_number, invoice_numbers)
        self.assertNotIn("FAC-OTHER", invoice_numbers)

    def test_delete_posted_receipt_reverts_stock_when_not_sold(self):
        receipt = self.create_posted_receipt()
        self.assertEqual(self.stock(), Decimal("2.00"))

        response = self.client.delete(f"/api/v1/purchase-receipts/{receipt.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(PurchaseReceipt.objects.filter(id=receipt.id).exists())
        self.assertIsNone(self.stock())

    def test_delete_posted_receipt_fails_if_any_item_was_sold(self):
        receipt = self.create_posted_receipt()
        InventoryMovement.objects.create(
            product=self.product,
            movement_type=MovementType.OUTBOUND,
            quantity_delta=Decimal("-1.00"),
            reference_type="sale_confirm",
            reference_id="sale-1",
            note="sale",
            created_by=self.cashier,
        )

        response = self.client.delete(f"/api/v1/purchase-receipts/{receipt.id}/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "receipt_has_sold_items")
        self.assertTrue(PurchaseReceipt.objects.filter(id=receipt.id).exists())

    def test_delete_posted_receipt_allows_if_stock_was_replenished(self):
        receipt = self.create_posted_receipt()
        InventoryMovement.objects.create(
            product=self.product,
            movement_type=MovementType.OUTBOUND,
            quantity_delta=Decimal("-1.00"),
            reference_type="sale_confirm",
            reference_id="sale-2",
            note="sale",
            created_by=self.cashier,
        )
        InventoryMovement.objects.create(
            product=self.product,
            movement_type=MovementType.ADJUSTMENT,
            quantity_delta=Decimal("1.00"),
            reference_type="manual_adjustment",
            reference_id="adj-1",
            note="restock",
            created_by=self.cashier,
        )

        response = self.client.delete(f"/api/v1/purchase-receipts/{receipt.id}/")
        self.assertEqual(response.status_code, 204)
