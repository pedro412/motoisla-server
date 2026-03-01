from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.layaway.models import (
    Customer,
    CustomerCredit,
    Layaway,
    LayawayExtensionLog,
    LayawayLine,
    LayawayPayment,
    normalize_phone,
)
from apps.sales.models import CardCommissionPlan, CardType, PaymentMethod


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "phone", "phone_normalized", "name", "notes", "created_at", "updated_at"]
        read_only_fields = ["id", "phone_normalized", "created_at", "updated_at"]


class CustomerUpsertSerializer(serializers.Serializer):
    phone = serializers.CharField()
    name = serializers.CharField()
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_phone(self, value):
        if not normalize_phone(value):
            raise serializers.ValidationError("El telefono es obligatorio.")
        return value


class LayawayLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = LayawayLine
        fields = ["id", "product", "product_sku", "product_name", "qty", "unit_price", "unit_cost", "discount_pct", "created_at"]
        read_only_fields = ["id", "created_at"]


class LayawayPaymentSerializer(serializers.ModelSerializer):
    card_plan_id = serializers.PrimaryKeyRelatedField(
        source="card_commission_plan",
        queryset=CardCommissionPlan.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        write_only=True,
    )

    class Meta:
        model = LayawayPayment
        fields = [
            "id",
            "method",
            "amount",
            "card_type",
            "card_plan_id",
            "card_plan_code",
            "card_plan_label",
            "installments_months",
            "commission_rate",
            "reference_type",
            "reference_id",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "card_plan_code",
            "card_plan_label",
            "installments_months",
            "commission_rate",
            "created_at",
        ]


class LayawayExtensionSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = LayawayExtensionLog
        fields = ["id", "old_expires_at", "new_expires_at", "reason", "created_by", "created_by_username", "created_at"]
        read_only_fields = fields


class CustomerCreditSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)

    class Meta:
        model = CustomerCredit
        fields = ["id", "customer", "customer_name", "customer_phone", "balance", "updated_at"]
        read_only_fields = ["id", "updated_at"]


class LayawaySerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)
    lines = LayawayLineSerializer(many=True, read_only=True)
    payments = LayawayPaymentSerializer(many=True, read_only=True)
    extensions = LayawayExtensionSerializer(many=True, read_only=True)
    balance_due = serializers.SerializerMethodField()
    customer_credit_balance = serializers.SerializerMethodField()

    class Meta:
        model = Layaway
        fields = [
            "id",
            "customer",
            "customer_name",
            "customer_phone",
            "subtotal",
            "total",
            "amount_paid",
            "total_price",
            "deposit_amount",
            "expires_at",
            "status",
            "notes",
            "settled_sale_id",
            "created_by",
            "created_at",
            "updated_at",
            "lines",
            "payments",
            "extensions",
            "balance_due",
            "customer_credit_balance",
        ]
        read_only_fields = fields

    def get_balance_due(self, obj):
        return str((obj.total - obj.amount_paid).quantize(Decimal("0.01")))

    def get_customer_credit_balance(self, obj):
        if not obj.customer_id or not hasattr(obj.customer, "credit"):
            return "0.00"
        return str(obj.customer.credit.balance.quantize(Decimal("0.01")))


class LayawayCreateSerializer(serializers.Serializer):
    customer = CustomerUpsertSerializer()
    lines = LayawayLineSerializer(many=True)
    deposit_payments = LayawayPaymentSerializer(many=True)
    expires_at = serializers.DateTimeField()
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        lines = attrs.get("lines", [])
        deposit_payments = attrs.get("deposit_payments", [])
        expires_at = attrs.get("expires_at")
        if not lines:
            raise serializers.ValidationError({"lines": "Debes incluir al menos una linea."})
        if not deposit_payments:
            raise serializers.ValidationError({"deposit_payments": "Debes incluir al menos un anticipo."})
        if expires_at <= timezone.now():
            raise serializers.ValidationError({"expires_at": "La vigencia debe estar en el futuro."})

        subtotal = Decimal("0.00")
        total = Decimal("0.00")
        seen_products = set()
        total_qty = Decimal("0.00")
        for line in lines:
            if line["qty"] <= 0:
                raise serializers.ValidationError({"lines": "La cantidad debe ser mayor a 0."})
            product_id = str(line["product"].id)
            if product_id in seen_products:
                raise serializers.ValidationError({"lines": "No puedes repetir productos dentro del mismo apartado."})
            seen_products.add(product_id)
            line_subtotal = (line["qty"] * line["unit_price"]).quantize(Decimal("0.01"))
            line_discount = ((line_subtotal * line.get("discount_pct", Decimal("0"))) / Decimal("100")).quantize(Decimal("0.01"))
            subtotal += line_subtotal
            total += line_subtotal - line_discount
            total_qty += line["qty"]

        deposit_total = self._validate_payments(deposit_payments, "deposit_payments")
        if deposit_total <= 0 or deposit_total > total:
            raise serializers.ValidationError(
                {"deposit_payments": "El anticipo debe ser mayor a 0 y no exceder el total del apartado."}
            )

        attrs["_subtotal"] = subtotal.quantize(Decimal("0.01"))
        attrs["_total"] = total.quantize(Decimal("0.01"))
        attrs["_deposit_total"] = deposit_total
        attrs["_total_qty"] = total_qty.quantize(Decimal("0.01"))
        return attrs

    @staticmethod
    def _legacy_card_type_for_plan(plan):
        if not plan:
            return None
        if plan.installments_months == 0:
            return CardType.NORMAL
        if plan.installments_months == 3:
            return CardType.MSI_3
        return None

    def _validate_payments(self, payments, field_name):
        payments_sum = Decimal("0.00")
        for payment in payments:
            if payment["amount"] <= 0:
                raise serializers.ValidationError({field_name: "Cada pago debe ser mayor a 0."})
            if payment["method"] == PaymentMethod.CUSTOMER_CREDIT:
                raise serializers.ValidationError({field_name: "El anticipo inicial no puede usar saldo a favor."})
            if payment["method"] == PaymentMethod.CARD:
                plan = payment.get("card_commission_plan")
                if not plan:
                    raise serializers.ValidationError({field_name: "Los pagos con tarjeta requieren card_plan_id."})
                payment["card_plan_code"] = plan.code
                payment["card_plan_label"] = plan.label
                payment["installments_months"] = plan.installments_months
                payment["commission_rate"] = plan.commission_rate
                payment["card_type"] = self._legacy_card_type_for_plan(plan) or payment.get("card_type") or ""
            else:
                payment["card_type"] = ""
                payment["card_plan_code"] = ""
                payment["card_plan_label"] = ""
                payment["installments_months"] = 0
                payment["commission_rate"] = None
            payment.pop("card_commission_plan", None)
            payments_sum += payment["amount"]
        return payments_sum.quantize(Decimal("0.01"))


class LayawayPaymentCreateSerializer(serializers.Serializer):
    payments = LayawayPaymentSerializer(many=True)

    def validate(self, attrs):
        payments = attrs.get("payments", [])
        if not payments:
            raise serializers.ValidationError({"payments": "Debes incluir al menos un pago."})
        payments_sum = Decimal("0.00")
        for payment in payments:
            if payment["amount"] <= 0:
                raise serializers.ValidationError({"payments": "Cada pago debe ser mayor a 0."})
            if payment["method"] == PaymentMethod.CARD:
                plan = payment.get("card_commission_plan")
                if not plan:
                    raise serializers.ValidationError({"payments": "Los pagos con tarjeta requieren card_plan_id."})
                payment["card_plan_code"] = plan.code
                payment["card_plan_label"] = plan.label
                payment["installments_months"] = plan.installments_months
                payment["commission_rate"] = plan.commission_rate
                payment["card_type"] = LayawayCreateSerializer._legacy_card_type_for_plan(plan) or payment.get("card_type") or ""
            else:
                payment["card_type"] = ""
                payment["card_plan_code"] = ""
                payment["card_plan_label"] = ""
                payment["installments_months"] = 0
                payment["commission_rate"] = None
            payment.pop("card_commission_plan", None)
            payments_sum += payment["amount"]
        attrs["_payments_sum"] = payments_sum.quantize(Decimal("0.01"))
        return attrs


class LayawayExtendSerializer(serializers.Serializer):
    new_expires_at = serializers.DateTimeField()
    reason = serializers.CharField(required=False, allow_blank=True)
