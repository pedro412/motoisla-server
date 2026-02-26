from django.contrib import admin

from apps.expenses.models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("category", "description", "amount", "expense_date", "created_by", "created_at")
    list_filter = ("category", "expense_date", "created_by")
    search_fields = ("category", "description", "created_by__username")
    autocomplete_fields = ("created_by",)
