from django.contrib import admin

from apps.layaway.models import Customer, CustomerCredit, Layaway, LayawayExtensionLog, LayawayLine, LayawayPayment


class LayawayPaymentInline(admin.TabularInline):
    model = LayawayPayment
    extra = 0


class LayawayLineInline(admin.TabularInline):
    model = LayawayLine
    extra = 0


@admin.register(Layaway)
class LayawayAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "customer_name",
        "customer_phone",
        "total",
        "amount_paid",
        "status",
        "expires_at",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "created_by")
    search_fields = ("customer_name", "customer_phone", "customer__name", "customer__phone")
    autocomplete_fields = ("customer", "product", "created_by")
    inlines = [LayawayLineInline, LayawayPaymentInline]


@admin.register(LayawayPayment)
class LayawayPaymentAdmin(admin.ModelAdmin):
    list_display = ("layaway", "method", "amount", "created_at")
    search_fields = ("layaway__id", "layaway__customer_name", "layaway__customer_phone")
    autocomplete_fields = ("layaway",)


@admin.register(LayawayLine)
class LayawayLineAdmin(admin.ModelAdmin):
    list_display = ("layaway", "product", "qty", "unit_price")
    search_fields = ("layaway__id", "product__sku", "product__name")
    autocomplete_fields = ("layaway", "product")


@admin.register(LayawayExtensionLog)
class LayawayExtensionLogAdmin(admin.ModelAdmin):
    list_display = ("layaway", "old_expires_at", "new_expires_at", "created_by", "created_at")
    search_fields = ("layaway__id", "layaway__customer_name", "layaway__customer_phone")
    autocomplete_fields = ("layaway", "created_by")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "updated_at")
    search_fields = ("name", "phone", "phone_normalized")


@admin.register(CustomerCredit)
class CustomerCreditAdmin(admin.ModelAdmin):
    list_display = ("customer", "customer_name", "customer_phone", "balance", "updated_at")
    search_fields = ("customer_name", "customer_phone", "customer__name", "customer__phone")
