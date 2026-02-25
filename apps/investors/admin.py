from django.contrib import admin

from apps.investors.models import Investor, InvestorAssignment


@admin.register(Investor)
class InvestorAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "is_active")
    search_fields = ("display_name", "user__username", "user__email")
    list_filter = ("is_active",)


@admin.register(InvestorAssignment)
class InvestorAssignmentAdmin(admin.ModelAdmin):
    list_display = ("investor", "product", "qty_assigned", "qty_sold", "unit_cost", "created_at")
    search_fields = ("investor__display_name", "product__sku", "product__name")
    list_filter = ("investor",)
