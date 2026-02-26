from rest_framework import viewsets

from apps.audit.services import record_audit
from apps.common.permissions import RolePermission
from apps.expenses.models import Expense
from apps.expenses.serializers import ExpenseSerializer


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.select_related("created_by")
    serializer_class = ExpenseSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["expenses.view"],
        "retrieve": ["expenses.view"],
        "create": ["expenses.manage"],
        "partial_update": ["expenses.manage"],
        "update": ["expenses.manage"],
        "destroy": ["expenses.manage"],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        category = self.request.query_params.get("category")
        if date_from:
            queryset = queryset.filter(expense_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(expense_date__lte=date_to)
        if category:
            queryset = queryset.filter(category__iexact=category.strip())
        return queryset

    def perform_create(self, serializer):
        expense = serializer.save()
        record_audit(
            actor=self.request.user,
            action="expenses.create",
            entity_type="expense",
            entity_id=expense.id,
            payload={
                "category": expense.category,
                "amount": str(expense.amount),
                "expense_date": str(expense.expense_date),
            },
        )

    def perform_update(self, serializer):
        expense = self.get_object()
        before = {
            "category": expense.category,
            "description": expense.description,
            "amount": str(expense.amount),
            "expense_date": str(expense.expense_date),
        }
        expense = serializer.save()
        after = {
            "category": expense.category,
            "description": expense.description,
            "amount": str(expense.amount),
            "expense_date": str(expense.expense_date),
        }
        record_audit(
            actor=self.request.user,
            action="expenses.update",
            entity_type="expense",
            entity_id=expense.id,
            payload={"before": before, "after": after},
        )

    def perform_destroy(self, instance):
        record_audit(
            actor=self.request.user,
            action="expenses.delete",
            entity_type="expense",
            entity_id=instance.id,
            payload={
                "category": instance.category,
                "amount": str(instance.amount),
                "expense_date": str(instance.expense_date),
            },
        )
        super().perform_destroy(instance)
