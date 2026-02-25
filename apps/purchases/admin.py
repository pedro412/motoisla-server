from django.contrib import admin

from apps.purchases.models import PurchaseReceipt, PurchaseReceiptLine


class PurchaseReceiptLineInline(admin.TabularInline):
    model = PurchaseReceiptLine
    extra = 0


@admin.register(PurchaseReceipt)
class PurchaseReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "supplier",
        "status",
        "invoice_number",
        "invoice_date",
        "total",
        "created_by",
        "posted_at",
        "created_at",
    )
    list_filter = ("status", "supplier")
    search_fields = ("invoice_number", "supplier__name", "supplier__code")
    autocomplete_fields = ("created_by",)
    inlines = [PurchaseReceiptLineInline]


@admin.register(PurchaseReceiptLine)
class PurchaseReceiptLineAdmin(admin.ModelAdmin):
    list_display = ("receipt", "product", "qty", "unit_cost", "unit_price")
    search_fields = ("receipt__invoice_number", "product__sku", "product__name")
    autocomplete_fields = ("receipt", "product")
