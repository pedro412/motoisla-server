from django.contrib import admin

from apps.ledger.models import LedgerEntry


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "investor",
        "entry_type",
        "capital_delta",
        "inventory_delta",
        "profit_delta",
        "reference_type",
        "reference_id",
        "created_at",
    )
    search_fields = ("investor__display_name", "reference_type", "reference_id", "note")
    list_filter = ("entry_type", "investor")
