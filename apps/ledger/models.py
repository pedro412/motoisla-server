import uuid

from django.db import models


class LedgerEntryType(models.TextChoices):
    CAPITAL_DEPOSIT = "CAPITAL_DEPOSIT", "Capital Deposit"
    CAPITAL_WITHDRAWAL = "CAPITAL_WITHDRAWAL", "Capital Withdrawal"
    CAPITAL_TO_INVENTORY = "CAPITAL_TO_INVENTORY", "Capital to Inventory"
    INVENTORY_TO_CAPITAL = "INVENTORY_TO_CAPITAL", "Inventory to Capital"
    PROFIT_SHARE = "PROFIT_SHARE", "Profit Share"
    REINVESTMENT = "REINVESTMENT", "Reinvestment"


class LedgerEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    investor = models.ForeignKey("investors.Investor", on_delete=models.CASCADE, related_name="ledger_entries")
    entry_type = models.CharField(max_length=32, choices=LedgerEntryType.choices)
    capital_delta = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    inventory_delta = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    profit_delta = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reference_type = models.CharField(max_length=64)
    reference_id = models.CharField(max_length=64)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
