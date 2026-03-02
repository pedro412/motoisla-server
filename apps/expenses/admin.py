from django.contrib import admin

from apps.expenses.models import Expense, FixedExpenseTemplate


@admin.register(FixedExpenseTemplate)
class FixedExpenseTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "default_amount", "charge_day", "is_active", "created_by", "updated_at")
    list_filter = ("is_active", "category", "charge_day")
    search_fields = ("name", "category", "description", "notes")
    autocomplete_fields = ("created_by",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "category",
        "description",
        "amount",
        "expense_type",
        "status",
        "expense_date",
        "month_bucket",
        "template",
        "created_by",
    )
    list_filter = ("expense_type", "status", "category", "month_bucket", "expense_date")
    search_fields = ("category", "description", "template__name", "created_by__username", "paid_by__username")
    autocomplete_fields = ("created_by", "paid_by", "template")
