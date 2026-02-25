import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import DecimalField
from django.db.models import Sum
from django.db.models.functions import Coalesce


class MovementType(models.TextChoices):
    INBOUND = "INBOUND", "Inbound"
    OUTBOUND = "OUTBOUND", "Outbound"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"
    RESERVED = "RESERVED", "Reserved"
    RELEASED = "RELEASED", "Released"


class InventoryMovement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity_delta = models.DecimalField(max_digits=12, decimal_places=2)
    reference_type = models.CharField(max_length=64)
    reference_id = models.CharField(max_length=64)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="inventory_movements")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["reference_type", "reference_id", "product"],
                name="unique_inventory_reference_product",
            )
        ]

    def clean(self):
        if self.quantity_delta == 0:
            raise ValidationError("quantity_delta cannot be zero")

        if self.quantity_delta < 0:
            available = self.current_stock(self.product_id)
            if available + self.quantity_delta < 0:
                raise ValidationError("insufficient stock")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @staticmethod
    def current_stock(product_id):
        result = InventoryMovement.objects.filter(product_id=product_id).aggregate(
            total=Coalesce(
                Sum("quantity_delta"),
                0,
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
        return result["total"]
