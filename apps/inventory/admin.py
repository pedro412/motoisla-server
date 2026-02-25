from django.contrib import admin

from apps.inventory.models import InventoryMovement


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "movement_type",
        "quantity_delta",
        "reference_type",
        "reference_id",
        "created_by",
        "created_at",
    )
    list_filter = ("movement_type", "created_by")
    search_fields = ("product__sku", "product__name", "reference_type", "reference_id", "note")
    autocomplete_fields = ("product", "created_by")
