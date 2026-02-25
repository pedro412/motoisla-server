from django.contrib import admin

from apps.layaway.models import CustomerCredit, Layaway, LayawayPayment


class LayawayPaymentInline(admin.TabularInline):
    model = LayawayPayment
    extra = 0


@admin.register(Layaway)
class LayawayAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "customer_name",
        "customer_phone",
        "qty",
        "total_price",
        "deposit_amount",
        "status",
        "expires_at",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "created_by")
    search_fields = ("customer_name", "customer_phone", "product__sku", "product__name")
    autocomplete_fields = ("product", "created_by")
    inlines = [LayawayPaymentInline]


@admin.register(LayawayPayment)
class LayawayPaymentAdmin(admin.ModelAdmin):
    list_display = ("layaway", "amount", "created_at")
    search_fields = ("layaway__id", "layaway__customer_name", "layaway__customer_phone")
    autocomplete_fields = ("layaway",)


@admin.register(CustomerCredit)
class CustomerCreditAdmin(admin.ModelAdmin):
    list_display = ("customer_name", "customer_phone", "balance", "updated_at")
    search_fields = ("customer_name", "customer_phone")
