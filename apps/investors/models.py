import uuid

from django.db import models


class Investor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="investor_profile")
    display_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.display_name


class InvestorAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investor = models.ForeignKey(Investor, on_delete=models.CASCADE, related_name="assignments")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="investor_assignments")
    qty_assigned = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    qty_sold = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["investor", "product", "unit_cost"], name="unique_assignment_tuple"),
            models.CheckConstraint(check=models.Q(qty_assigned__gt=0), name="investor_assignment_qty_assigned_gt_zero"),
            models.CheckConstraint(check=models.Q(unit_cost__gte=0), name="investor_assignment_unit_cost_gte_zero"),
            models.CheckConstraint(check=models.Q(qty_sold__gte=0), name="investor_assignment_qty_sold_gte_zero"),
            models.CheckConstraint(check=models.Q(qty_sold__lte=models.F("qty_assigned")), name="investor_assignment_qty_sold_lte_assigned"),
        ]
