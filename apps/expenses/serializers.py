from datetime import datetime

from django.utils import timezone
from rest_framework import serializers

from apps.expenses.models import Expense, ExpenseStatus, ExpenseType, FixedExpenseTemplate


class FixedExpenseTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FixedExpenseTemplate
        fields = [
            "id",
            "name",
            "category",
            "default_amount",
            "description",
            "charge_day",
            "is_active",
            "notes",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("name is required")
        return value

    def validate_category(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("category is required")
        return value

    def validate_default_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("default_amount must be greater than 0")
        return value

    def validate_charge_day(self, value):
        if value < 1 or value > 28:
            raise serializers.ValidationError("charge_day must be between 1 and 28")
        return value

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class ExpenseSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True)
    paid_by_username = serializers.CharField(source="paid_by.username", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Expense
        fields = [
            "id",
            "category",
            "description",
            "amount",
            "expense_date",
            "expense_type",
            "status",
            "template",
            "template_name",
            "due_date",
            "paid_at",
            "month_bucket",
            "paid_by",
            "paid_by_username",
            "created_by",
            "created_by_username",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "paid_at",
            "month_bucket",
            "paid_by",
            "paid_by_username",
            "created_by",
            "created_by_username",
            "created_at",
            "template_name",
        ]

    def validate_category(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("category is required")
        return value

    def validate_description(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("description is required")
        return value

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("amount must be greater than 0")
        return value

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        expense_type = attrs.get("expense_type", instance.expense_type if instance else ExpenseType.VARIABLE)
        status = attrs.get("status", instance.status if instance else ExpenseStatus.PAID)
        template = attrs.get("template", instance.template if instance else None)

        if expense_type == ExpenseType.VARIABLE and template is not None:
            raise serializers.ValidationError({"template": "variable expenses cannot reference a fixed template"})
        if expense_type == ExpenseType.FIXED and template is None:
            raise serializers.ValidationError({"template": "fixed expenses require a template"})
        if instance and instance.status == ExpenseStatus.CANCELLED and status == ExpenseStatus.PENDING:
            raise serializers.ValidationError({"status": "cancelled expenses cannot move back to pending"})
        if status == ExpenseStatus.PAID and not attrs.get("expense_date") and not (instance and instance.expense_date):
            raise serializers.ValidationError({"expense_date": "expense_date is required when marking an expense as paid"})
        return attrs

    @staticmethod
    def _month_bucket_for(expense_date):
        return expense_date.replace(day=1)

    def _apply_payment_fields(self, validated_data):
        status = validated_data.get("status", self.instance.status if self.instance else ExpenseStatus.PAID)
        request = self.context["request"]
        if status == ExpenseStatus.PAID:
            validated_data["paid_at"] = timezone.now()
            validated_data["paid_by"] = request.user
        else:
            validated_data["paid_at"] = None
            validated_data["paid_by"] = None
        expense_date = validated_data.get("expense_date") or (self.instance.expense_date if self.instance else None)
        if expense_date:
            validated_data["month_bucket"] = self._month_bucket_for(expense_date)
        due_date = validated_data.get("due_date")
        if due_date is None and expense_date and not self.instance:
            validated_data["due_date"] = expense_date
        elif due_date is None and not self.instance:
            validated_data["due_date"] = validated_data.get("expense_date")

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        if "expense_type" not in validated_data:
            validated_data["expense_type"] = ExpenseType.VARIABLE
        if "status" not in validated_data:
            validated_data["status"] = ExpenseStatus.PAID
        self._apply_payment_fields(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        status = validated_data.get("status", instance.status)
        if status == ExpenseStatus.PAID and instance.status == ExpenseStatus.PAID:
            validated_data.setdefault("paid_at", instance.paid_at or timezone.now())
            validated_data.setdefault("paid_by", instance.paid_by or self.context["request"].user)
        else:
            self._apply_payment_fields(validated_data)

        expense_date = validated_data.get("expense_date")
        if expense_date:
            validated_data["month_bucket"] = self._month_bucket_for(expense_date)
        elif "month_bucket" not in validated_data:
            validated_data["month_bucket"] = instance.month_bucket
        return super().update(instance, validated_data)


class GenerateFixedExpensesSerializer(serializers.Serializer):
    month = serializers.RegexField(r"^\d{4}-\d{2}$")

    def validate_month(self, value):
        try:
            datetime.strptime(value, "%Y-%m")
        except ValueError as exc:
            raise serializers.ValidationError("month must use YYYY-MM format") from exc
        return value


class ExpenseSummaryQuerySerializer(serializers.Serializer):
    month = serializers.RegexField(r"^\d{4}-\d{2}$")

    def validate_month(self, value):
        try:
            datetime.strptime(value, "%Y-%m")
        except ValueError as exc:
            raise serializers.ValidationError("month must use YYYY-MM format") from exc
        return value
