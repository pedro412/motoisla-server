from rest_framework import serializers

from apps.investors.models import Investor, InvestorAssignment
from apps.ledger.models import LedgerEntry


class InvestorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Investor
        fields = ["id", "user", "display_name", "is_active"]


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "investor",
            "entry_type",
            "capital_delta",
            "inventory_delta",
            "profit_delta",
            "reference_type",
            "reference_id",
            "note",
            "created_at",
        ]


class InvestorAssignmentSerializer(serializers.ModelSerializer):
    qty_available = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = InvestorAssignment
        fields = [
            "id",
            "investor",
            "product",
            "qty_assigned",
            "qty_sold",
            "qty_available",
            "unit_cost",
            "created_at",
        ]
        read_only_fields = ["id", "qty_sold", "created_at", "qty_available"]

    def validate(self, attrs):
        qty = attrs.get("qty_assigned")
        if qty is not None and qty <= 0:
            raise serializers.ValidationError({"qty_assigned": "La cantidad asignada debe ser mayor a 0."})
        unit_cost = attrs.get("unit_cost")
        if unit_cost is not None and unit_cost < 0:
            raise serializers.ValidationError({"unit_cost": "El costo unitario debe ser mayor o igual a 0."})
        return attrs


class InvestorAmountSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    note = serializers.CharField(required=False, allow_blank=True)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto debe ser mayor a 0.")
        return value
