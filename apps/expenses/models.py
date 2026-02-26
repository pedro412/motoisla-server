import uuid

from django.db import models


class Expense(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=80)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    expense_date = models.DateField()
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]
        indexes = [
            models.Index(fields=["expense_date"], name="expense_date_idx"),
            models.Index(fields=["category", "expense_date"], name="expense_category_date_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name="expense_amount_gt_zero"),
        ]
