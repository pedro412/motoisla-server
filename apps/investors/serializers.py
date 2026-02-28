from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.catalog.models import Product
from apps.investors.models import Investor, InvestorAssignment
from apps.ledger.models import LedgerEntry
from apps.ledger.services import create_capital_deposit, current_balances


def format_decimal(value: Decimal | str | int | float | None):
    amount = Decimal(value or "0").quantize(Decimal("0.01"))
    return f"{amount:.2f}"


class InvestorSerializer(serializers.ModelSerializer):
    initial_capital = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, write_only=True)
    balances = serializers.SerializerMethodField()

    class Meta:
        model = Investor
        fields = ["id", "user", "display_name", "is_active", "initial_capital", "balances"]
        read_only_fields = ["id", "balances"]
        extra_kwargs = {
            "user": {
                "required": False,
                "allow_null": True,
            }
        }

    def validate_initial_capital(self, value):
        if value < 0:
            raise serializers.ValidationError("El capital inicial debe ser mayor o igual a 0.")
        return value

    def get_balances(self, obj):
        capital = getattr(obj, "balance_capital", None)
        inventory = getattr(obj, "balance_inventory", None)
        profit = getattr(obj, "balance_profit", None)

        if capital is None or inventory is None or profit is None:
            balances = current_balances(obj)
            capital = balances["capital"]
            inventory = balances["inventory"]
            profit = balances["profit"]

        return {
            "capital": format_decimal(capital),
            "inventory": format_decimal(inventory),
            "profit": format_decimal(profit),
        }

    def create(self, validated_data):
        initial_capital = validated_data.pop("initial_capital", Decimal("0.00"))

        with transaction.atomic():
            investor = super().create(validated_data)
            if initial_capital > 0:
                create_capital_deposit(
                    investor=investor,
                    amount=initial_capital,
                    reference_type="initial_capital",
                    reference_id=str(investor.id),
                    note="Initial capital",
                )

        return investor


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
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = InvestorAssignment
        fields = [
            "id",
            "investor",
            "product",
            "product_sku",
            "product_name",
            "qty_assigned",
            "qty_sold",
            "qty_available",
            "unit_cost",
            "line_total",
            "created_at",
        ]
        read_only_fields = ["id", "qty_sold", "created_at", "qty_available", "product_sku", "product_name", "line_total"]

    def validate(self, attrs):
        qty = attrs.get("qty_assigned")
        if qty is not None and qty <= 0:
            raise serializers.ValidationError({"qty_assigned": "La cantidad asignada debe ser mayor a 0."})
        unit_cost = attrs.get("unit_cost")
        if unit_cost is not None and unit_cost < 0:
            raise serializers.ValidationError({"unit_cost": "El costo unitario debe ser mayor o igual a 0."})
        return attrs

    def get_line_total(self, obj):
        return format_decimal(obj.qty_assigned * obj.unit_cost)


class InvestorAmountSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    note = serializers.CharField(required=False, allow_blank=True)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto debe ser mayor a 0.")
        return value


class InvestorPurchaseLineSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    qty = serializers.DecimalField(max_digits=12, decimal_places=2)
    unit_cost_gross = serializers.DecimalField(max_digits=12, decimal_places=2)

    def validate_qty(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a 0.")
        return value

    def validate_unit_cost_gross(self, value):
        if value <= 0:
            raise serializers.ValidationError("El costo unitario debe ser mayor a 0.")
        return value


class InvestorPurchaseSerializer(serializers.Serializer):
    tax_rate_pct = serializers.DecimalField(max_digits=5, decimal_places=2)
    lines = InvestorPurchaseLineSerializer(many=True)

    def validate_tax_rate_pct(self, value):
        if value < 0:
            raise serializers.ValidationError("La tasa de IVA debe ser mayor o igual a 0.")
        return value

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("Debes enviar al menos una línea.")
        return value
