import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class SaleStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    CONFIRMED = "CONFIRMED", "Confirmed"
    VOID = "VOID", "Void"


class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Cash"
    CARD = "CARD", "Card"
    CUSTOMER_CREDIT = "CUSTOMER_CREDIT", "Customer Credit"


class CardType(models.TextChoices):
    NORMAL = "NORMAL", "Normal"
    MSI_3 = "MSI_3", "3MSI"


CARD_NORMAL_COMMISSION = Decimal("0.02")
CARD_MSI3_COMMISSION = Decimal("0.0558")
LEGACY_CARD_TYPE_TO_RATE = {
    CardType.NORMAL: CARD_NORMAL_COMMISSION,
    CardType.MSI_3: CARD_MSI3_COMMISSION,
}


class Sale(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cashier = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="sales")
    customer = models.ForeignKey("layaway.Customer", on_delete=models.PROTECT, null=True, blank=True, related_name="sales")
    status = models.CharField(max_length=16, choices=SaleStatus.choices, default=SaleStatus.DRAFT)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "confirmed_at"], name="sale_status_confirmed_idx"),
            models.Index(fields=["cashier", "created_at"], name="sale_cashier_created_idx"),
        ]


class SaleLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        indexes = [
            models.Index(fields=["product"], name="saleline_product_idx"),
        ]

    def clean(self):
        if self.qty <= 0:
            raise ValidationError("qty must be greater than 0")
        if self.discount_pct < 0 or self.discount_pct > 100:
            raise ValidationError("discount_pct must be between 0 and 100")


class CardCommissionPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=32, unique=True)
    label = models.CharField(max_length=64)
    installments_months = models.PositiveIntegerField(default=0)
    commission_rate = models.DecimalField(max_digits=6, decimal_places=4)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "installments_months", "label"]
        indexes = [
            models.Index(fields=["is_active", "sort_order"], name="cardplan_active_sort_idx"),
        ]

    def __str__(self):
        return self.label


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    card_type = models.CharField(max_length=12, choices=CardType.choices, null=True, blank=True)
    card_commission_plan = models.ForeignKey(
        CardCommissionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )
    commission_rate = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    card_plan_code = models.CharField(max_length=32, blank=True, default="")
    card_plan_label = models.CharField(max_length=64, blank=True, default="")
    installments_months = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["method"], name="payment_method_idx"),
            models.Index(fields=["card_type"], name="payment_card_type_idx"),
            models.Index(fields=["sale", "method"], name="payment_sale_method_idx"),
        ]


class VoidEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name="void_event")
    reason = models.CharField(max_length=255)
    actor = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
