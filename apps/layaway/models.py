import uuid

from django.db import models


class LayawayStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    SETTLED = "SETTLED", "Settled"
    EXPIRED = "EXPIRED", "Expired"


class Layaway(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    customer_name = models.CharField(max_length=255)
    customer_phone = models.CharField(max_length=50, blank=True)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=LayawayStatus.choices, default=LayawayStatus.ACTIVE)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "expires_at"], name="layaway_status_expires_idx"),
            models.Index(fields=["customer_phone"], name="layaway_customer_phone_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(qty__gt=0), name="layaway_qty_gt_zero"),
            models.CheckConstraint(check=models.Q(total_price__gt=0), name="layaway_total_gt_zero"),
            models.CheckConstraint(check=models.Q(deposit_amount__gt=0), name="layaway_deposit_gt_zero"),
        ]


class LayawayPayment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    layaway = models.ForeignKey(Layaway, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)


class CustomerCredit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_name = models.CharField(max_length=255)
    customer_phone = models.CharField(max_length=50, blank=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["customer_phone"], name="customercredit_phone_idx"),
            models.Index(fields=["customer_name", "customer_phone"], name="customercredit_name_phone_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(balance__gte=0), name="customer_credit_balance_gte_zero"),
        ]
