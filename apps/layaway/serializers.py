from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.layaway.models import CustomerCredit, Layaway, LayawayPayment


class LayawayPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LayawayPayment
        fields = ["id", "amount", "created_at"]
        read_only_fields = ["id", "created_at"]


class LayawaySerializer(serializers.ModelSerializer):
    payments = LayawayPaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Layaway
        fields = [
            "id",
            "product",
            "qty",
            "customer_name",
            "customer_phone",
            "total_price",
            "deposit_amount",
            "expires_at",
            "status",
            "created_by",
            "created_at",
            "payments",
        ]
        read_only_fields = ["id", "status", "created_by", "created_at", "payments"]

    def validate(self, attrs):
        total = attrs.get("total_price", Decimal("0")).quantize(Decimal("0.01"))
        deposit = attrs.get("deposit_amount", Decimal("0")).quantize(Decimal("0.01"))
        qty = attrs.get("qty", Decimal("0"))
        expires_at = attrs.get("expires_at")

        if qty <= 0:
            raise serializers.ValidationError({"qty": "La cantidad debe ser mayor a 0."})
        if total <= 0:
            raise serializers.ValidationError({"total_price": "El total del apartado debe ser mayor a 0."})
        if deposit <= 0 or deposit > total:
            raise serializers.ValidationError({"deposit_amount": "El anticipo debe ser mayor a 0 y no exceder el total."})
        if expires_at is None:
            raise serializers.ValidationError({"expires_at": "La vigencia es obligatoria."})
        if expires_at <= timezone.now():
            raise serializers.ValidationError({"expires_at": "La vigencia debe estar en el futuro."})
        return attrs

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class CustomerCreditSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerCredit
        fields = ["id", "customer_name", "customer_phone", "balance", "updated_at"]
        read_only_fields = ["id", "updated_at"]
