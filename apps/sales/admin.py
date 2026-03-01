from django.contrib import admin

from apps.sales.models import CardCommissionPlan, Payment, Sale, SaleLine, VoidEvent


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("id", "cashier", "customer", "status", "subtotal", "discount_amount", "total", "confirmed_at", "created_at")
    list_filter = ("status", "cashier")
    search_fields = ("id", "cashier__username", "customer__name", "customer__phone")
    autocomplete_fields = ("cashier", "customer")
    inlines = [SaleLineInline, PaymentInline]


@admin.register(SaleLine)
class SaleLineAdmin(admin.ModelAdmin):
    list_display = ("sale", "product", "qty", "unit_price", "unit_cost", "discount_pct")
    search_fields = ("sale__id", "product__sku", "product__name")
    autocomplete_fields = ("sale", "product")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("sale", "method", "card_type", "card_plan_label", "commission_rate", "amount")
    list_filter = ("method", "card_type", "card_plan_code")
    search_fields = ("sale__id",)
    autocomplete_fields = ("sale",)


@admin.register(CardCommissionPlan)
class CardCommissionPlanAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "installments_months", "commission_rate", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("label", "code")
    ordering = ("sort_order", "installments_months", "label")


@admin.register(VoidEvent)
class VoidEventAdmin(admin.ModelAdmin):
    list_display = ("sale", "actor", "reason", "created_at")
    search_fields = ("sale__id", "actor__username", "reason")
    autocomplete_fields = ("sale", "actor")
