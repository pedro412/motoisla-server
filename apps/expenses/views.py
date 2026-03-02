from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.audit.services import record_audit
from apps.common.permissions import RolePermission
from apps.expenses.models import Expense, ExpenseStatus, ExpenseType, FixedExpenseTemplate
from apps.expenses.serializers import (
    ExpenseSerializer,
    ExpenseSummaryQuerySerializer,
    FixedExpenseTemplateSerializer,
    GenerateFixedExpensesSerializer,
)


def parse_month_bucket(month_value: str) -> date:
    month_start = datetime.strptime(month_value, "%Y-%m").date()
    return month_start.replace(day=1)


class FixedExpenseTemplateViewSet(viewsets.ModelViewSet):
    queryset = FixedExpenseTemplate.objects.select_related("created_by")
    serializer_class = FixedExpenseTemplateSerializer
    permission_classes = [RolePermission]
    http_method_names = ["get", "post", "patch", "head", "options"]
    capability_map = {
        "list": ["expenses.view"],
        "retrieve": ["expenses.view"],
        "create": ["expenses.manage"],
        "partial_update": ["expenses.manage"],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        is_active = self.request.query_params.get("is_active")
        category = self.request.query_params.get("category")
        q = self.request.query_params.get("q")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        if category:
            queryset = queryset.filter(category__iexact=category.strip())
        if q:
            term = q.strip()
            queryset = queryset.filter(Q(name__icontains=term) | Q(description__icontains=term) | Q(category__icontains=term))
        return queryset

    def perform_create(self, serializer):
        template = serializer.save()
        record_audit(
            actor=self.request.user,
            action="expenses.template.create",
            entity_type="fixed_expense_template",
            entity_id=template.id,
            payload={
                "name": template.name,
                "category": template.category,
                "default_amount": str(template.default_amount),
                "charge_day": template.charge_day,
                "is_active": template.is_active,
            },
        )

    def perform_update(self, serializer):
        template = self.get_object()
        before = {
            "name": template.name,
            "category": template.category,
            "default_amount": str(template.default_amount),
            "charge_day": template.charge_day,
            "is_active": template.is_active,
        }
        template = serializer.save()
        after = {
            "name": template.name,
            "category": template.category,
            "default_amount": str(template.default_amount),
            "charge_day": template.charge_day,
            "is_active": template.is_active,
        }
        record_audit(
            actor=self.request.user,
            action="expenses.template.update",
            entity_type="fixed_expense_template",
            entity_id=template.id,
            payload={"before": before, "after": after},
        )


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.select_related("created_by", "paid_by", "template")
    serializer_class = ExpenseSerializer
    permission_classes = [RolePermission]
    http_method_names = ["get", "post", "patch", "head", "options"]
    capability_map = {
        "list": ["expenses.view"],
        "retrieve": ["expenses.view"],
        "create": ["expenses.manage"],
        "partial_update": ["expenses.manage"],
        "summary": ["expenses.view"],
        "generate_fixed": ["expenses.manage"],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        category = self.request.query_params.get("category")
        month_value = self.request.query_params.get("month")
        status_value = self.request.query_params.get("status")
        expense_type = self.request.query_params.get("expense_type")
        template = self.request.query_params.get("template")

        if date_from:
            queryset = queryset.filter(expense_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(expense_date__lte=date_to)
        if category:
            queryset = queryset.filter(category__iexact=category.strip())
        if month_value:
            try:
                month_bucket = parse_month_bucket(month_value)
            except ValueError as exc:
                raise ValidationError({"month": "month must use YYYY-MM format"}) from exc
            queryset = queryset.filter(month_bucket=month_bucket)
        if status_value:
            queryset = queryset.filter(status=status_value)
        if expense_type:
            queryset = queryset.filter(expense_type=expense_type)
        if template:
            queryset = queryset.filter(template_id=template)
        return queryset

    @staticmethod
    def _category_breakdown(queryset):
        return list(
            queryset.values("category")
            .annotate(
                total_amount=Coalesce(
                    Sum("amount"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=16, decimal_places=2),
                ),
                items_count=Count("id"),
            )
            .order_by("-total_amount", "category")
        )

    @classmethod
    def build_summary_payload(cls, month_bucket: date):
        monthly = Expense.objects.filter(month_bucket=month_bucket)
        fixed_pending = monthly.filter(expense_type=ExpenseType.FIXED, status=ExpenseStatus.PENDING)
        fixed_paid = monthly.filter(expense_type=ExpenseType.FIXED, status=ExpenseStatus.PAID)
        variable_paid = monthly.filter(expense_type=ExpenseType.VARIABLE, status=ExpenseStatus.PAID)
        paid = monthly.filter(status=ExpenseStatus.PAID)
        pending = monthly.filter(status=ExpenseStatus.PENDING)

        fixed_pending_total = fixed_pending.aggregate(
            total=Coalesce(Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField(max_digits=16, decimal_places=2))
        )["total"]
        fixed_paid_total = fixed_paid.aggregate(
            total=Coalesce(Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField(max_digits=16, decimal_places=2))
        )["total"]
        variable_paid_total = variable_paid.aggregate(
            total=Coalesce(Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField(max_digits=16, decimal_places=2))
        )["total"]
        actual_paid_total = paid.aggregate(
            total=Coalesce(Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField(max_digits=16, decimal_places=2))
        )["total"]
        pending_commitments_total = pending.aggregate(
            total=Coalesce(Sum("amount"), Value(Decimal("0.00")), output_field=DecimalField(max_digits=16, decimal_places=2))
        )["total"]

        return {
            "month": month_bucket.strftime("%Y-%m"),
            "fixed_pending_total": fixed_pending_total,
            "fixed_paid_total": fixed_paid_total,
            "variable_paid_total": variable_paid_total,
            "actual_paid_total": actual_paid_total,
            "pending_commitments_total": pending_commitments_total,
            "fixed_pending_count": fixed_pending.count(),
            "fixed_paid_count": fixed_paid.count(),
            "variable_paid_count": variable_paid.count(),
            "by_category_paid": cls._category_breakdown(paid),
            "by_category_pending": cls._category_breakdown(pending),
        }

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
                "expense_type": expense.expense_type,
                "status": expense.status,
                "template_id": str(expense.template_id) if expense.template_id else None,
            },
        )

    def perform_update(self, serializer):
        expense = self.get_object()
        before = {
            "category": expense.category,
            "description": expense.description,
            "amount": str(expense.amount),
            "expense_date": str(expense.expense_date),
            "expense_type": expense.expense_type,
            "status": expense.status,
            "template_id": str(expense.template_id) if expense.template_id else None,
        }
        expense = serializer.save()
        after = {
            "category": expense.category,
            "description": expense.description,
            "amount": str(expense.amount),
            "expense_date": str(expense.expense_date),
            "expense_type": expense.expense_type,
            "status": expense.status,
            "template_id": str(expense.template_id) if expense.template_id else None,
        }
        record_audit(
            actor=self.request.user,
            action="expenses.update",
            entity_type="expense",
            entity_id=expense.id,
            payload={"before": before, "after": after},
        )

    @action(detail=False, methods=["post"], url_path="generate-fixed")
    def generate_fixed(self, request, *args, **kwargs):
        serializer = GenerateFixedExpensesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        month_bucket = parse_month_bucket(serializer.validated_data["month"])
        created_count = 0
        existing_count = 0

        for template in FixedExpenseTemplate.objects.filter(is_active=True).order_by("name"):
            due_date = month_bucket.replace(day=min(template.charge_day, monthrange(month_bucket.year, month_bucket.month)[1]))
            defaults = {
                "category": template.category,
                "description": template.description or template.name,
                "amount": template.default_amount,
                "expense_date": due_date,
                "expense_type": ExpenseType.FIXED,
                "status": ExpenseStatus.PENDING,
                "due_date": due_date,
                "created_by": request.user,
            }
            _, created = Expense.objects.get_or_create(
                template=template,
                month_bucket=month_bucket,
                defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                existing_count += 1

        summary = self.build_summary_payload(month_bucket)
        record_audit(
            actor=request.user,
            action="expenses.generate_fixed",
            entity_type="expense_generation",
            entity_id=f"{month_bucket:%Y-%m}",
            payload={
                "month": f"{month_bucket:%Y-%m}",
                "created_count": created_count,
                "existing_count": existing_count,
            },
        )
        return Response(
            {
                "month": f"{month_bucket:%Y-%m}",
                "created_count": created_count,
                "existing_count": existing_count,
                "summary": summary,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request, *args, **kwargs):
        serializer = ExpenseSummaryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        month_bucket = parse_month_bucket(serializer.validated_data["month"])
        return Response(self.build_summary_payload(month_bucket))
