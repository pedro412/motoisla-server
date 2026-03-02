import uuid
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models


class ExpenseType(models.TextChoices):
    FIXED = "FIXED", "Fixed"
    VARIABLE = "VARIABLE", "Variable"


class ExpenseStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PAID = "PAID", "Paid"
    CANCELLED = "CANCELLED", "Cancelled"


class FixedExpenseTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, db_index=True)
    category = models.CharField(max_length=80, db_index=True)
    default_amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    charge_day = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="fixed_expense_templates")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "category"]
        indexes = [
            models.Index(fields=["is_active", "category"], name="fixedexp_active_cat_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(default_amount__gt=0), name="fixedexp_amount_gt_zero"),
            models.CheckConstraint(check=models.Q(charge_day__gte=1) & models.Q(charge_day__lte=28), name="fixedexp_charge_day_valid"),
        ]

    def clean(self):
        self.name = (self.name or "").strip()
        self.category = (self.category or "").strip()
        self.description = (self.description or "").strip()
        self.notes = (self.notes or "").strip()
        if not self.name:
            raise ValidationError({"name": "name is required"})
        if not self.category:
            raise ValidationError({"category": "category is required"})
        if self.default_amount is not None and self.default_amount <= 0:
            raise ValidationError({"default_amount": "default_amount must be greater than 0"})
        if self.charge_day < 1 or self.charge_day > 28:
            raise ValidationError({"charge_day": "charge_day must be between 1 and 28"})


class Expense(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=80)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    expense_date = models.DateField()
    expense_type = models.CharField(max_length=12, choices=ExpenseType.choices, default=ExpenseType.VARIABLE, db_index=True)
    status = models.CharField(max_length=12, choices=ExpenseStatus.choices, default=ExpenseStatus.PAID, db_index=True)
    template = models.ForeignKey(
        FixedExpenseTemplate,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="expenses",
    )
    due_date = models.DateField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    month_bucket = models.DateField(default=date.today, db_index=True)
    paid_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="paid_expenses",
    )
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="created_expenses")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-month_bucket", "-expense_date", "-created_at"]
        indexes = [
            models.Index(fields=["expense_date"], name="expense_date_idx"),
            models.Index(fields=["category", "expense_date"], name="expense_category_date_idx"),
            models.Index(fields=["month_bucket", "status"], name="expense_month_status_idx"),
            models.Index(fields=["expense_type", "month_bucket"], name="expense_type_month_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name="expense_amount_gt_zero"),
            models.UniqueConstraint(
                fields=["template", "month_bucket"],
                condition=models.Q(template__isnull=False),
                name="expense_template_month_unique",
            ),
        ]

    def clean(self):
        self.category = (self.category or "").strip()
        self.description = (self.description or "").strip()
        if not self.category:
            raise ValidationError({"category": "category is required"})
        if not self.description:
            raise ValidationError({"description": "description is required"})
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "amount must be greater than 0"})
        if self.expense_type == ExpenseType.VARIABLE and self.template_id:
            raise ValidationError({"template": "variable expenses cannot reference a fixed template"})
        if self.expense_type == ExpenseType.FIXED and not self.template_id:
            raise ValidationError({"template": "fixed expenses require a template"})
        if self.month_bucket:
            self.month_bucket = self.month_bucket.replace(day=1)
        if not self.due_date:
            self.due_date = self.expense_date
