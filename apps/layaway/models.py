import re
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


def normalize_phone(value):
    raw = str(value or "").strip()
    normalized = re.sub(r"\D+", "", raw)
    return normalized or raw


class LayawayStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    SETTLED = "SETTLED", "Settled"
    EXPIRED = "EXPIRED", "Expired"
    REFUNDED = "REFUNDED", "Refunded"


class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=50)
    phone_normalized = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["phone_normalized"], name="customer_phone_norm_idx"),
            models.Index(fields=["name"], name="customer_name_idx"),
        ]

    def clean(self):
        if not self.phone:
            raise ValidationError("phone is required")
        normalized = normalize_phone(self.phone)
        if not normalized:
            raise ValidationError("phone must contain at least one digit")
        self.phone_normalized = normalized

    def save(self, *args, **kwargs):
        self.phone = str(self.phone or "").strip()
        self.name = str(self.name or "").strip()
        self.phone_normalized = normalize_phone(self.phone)
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def get_or_create_by_phone(cls, phone, name="", notes=""):
        normalized = normalize_phone(phone)
        customer = cls.objects.filter(phone_normalized=normalized).first()
        if customer:
            updated_fields = []
            if phone and customer.phone != str(phone).strip():
                customer.phone = str(phone).strip()
                updated_fields.append("phone")
            if name and customer.name != str(name).strip():
                customer.name = str(name).strip()
                updated_fields.append("name")
            if notes and customer.notes != str(notes).strip():
                customer.notes = str(notes).strip()
                updated_fields.append("notes")
            if updated_fields:
                customer.phone_normalized = normalize_phone(customer.phone)
                updated_fields.extend(["phone_normalized", "updated_at"])
                customer.save(update_fields=updated_fields)
            return customer
        return cls.objects.create(phone=str(phone).strip(), name=str(name).strip(), notes=str(notes).strip())

    def __str__(self):
        return f"{self.name} ({self.phone})"


class Layaway(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey("layaway.Customer", on_delete=models.PROTECT, null=True, blank=True, related_name="layaways")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    customer_name = models.CharField(max_length=255)
    customer_phone = models.CharField(max_length=50, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=LayawayStatus.choices, default=LayawayStatus.ACTIVE)
    notes = models.CharField(max_length=255, blank=True)
    settled_sale_id = models.UUIDField(null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "expires_at"], name="layaway_status_expires_idx"),
            models.Index(fields=["customer_phone"], name="layaway_customer_phone_idx"),
            models.Index(fields=["customer", "status"], name="layaway_customer_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(qty__gt=0), name="layaway_qty_gt_zero"),
            models.CheckConstraint(check=models.Q(total_price__gt=0), name="layaway_total_gt_zero"),
            models.CheckConstraint(check=models.Q(deposit_amount__gt=0), name="layaway_deposit_gt_zero"),
            models.CheckConstraint(check=models.Q(amount_paid__gte=0), name="layaway_amount_paid_gte_zero"),
        ]

    @property
    def balance_due(self):
        return (self.total - self.amount_paid).quantize(Decimal("0.01"))


class LayawayPayment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    layaway = models.ForeignKey(Layaway, on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=20, default="CASH")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    card_type = models.CharField(max_length=12, blank=True, default="")
    card_plan_code = models.CharField(max_length=32, blank=True, default="")
    card_plan_label = models.CharField(max_length=64, blank=True, default="")
    installments_months = models.PositiveIntegerField(default=0)
    commission_rate = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="layaway_payments")
    reference_type = models.CharField(max_length=64, blank=True, default="")
    reference_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class LayawayLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    layaway = models.ForeignKey(Layaway, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["layaway", "product"], name="layline_lay_prod_idx"),
        ]


class LayawayExtensionLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    layaway = models.ForeignKey(Layaway, on_delete=models.CASCADE, related_name="extensions")
    old_expires_at = models.DateTimeField()
    new_expires_at = models.DateTimeField()
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="layaway_extensions")
    created_at = models.DateTimeField(auto_now_add=True)


class CustomerCredit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.OneToOneField("layaway.Customer", on_delete=models.PROTECT, null=True, blank=True, related_name="credit")
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

    def save(self, *args, **kwargs):
        if self.customer:
            self.customer_name = self.customer.name
            self.customer_phone = self.customer.phone
        super().save(*args, **kwargs)
