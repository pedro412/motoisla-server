from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import UserRole
from apps.audit.services import record_audit
from apps.layaway.models import Customer, CustomerCredit, normalize_phone
from apps.sales.models import (
    CardCommissionPlan,
    CardType,
    Payment,
    PaymentMethod,
    Sale,
    SaleLine,
    SaleStatus,
)

VOID_WINDOW_MINUTES = 10


class SaleLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = SaleLine
        fields = ["id", "product", "product_sku", "product_name", "qty", "unit_price", "unit_cost", "discount_pct"]
        read_only_fields = ["id"]


class PaymentSerializer(serializers.ModelSerializer):
    card_plan_id = serializers.PrimaryKeyRelatedField(
        source="card_commission_plan",
        queryset=CardCommissionPlan.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Payment
        fields = [
            "id",
            "method",
            "amount",
            "card_type",
            "card_plan_id",
            "commission_rate",
            "card_plan_code",
            "card_plan_label",
            "installments_months",
        ]
        read_only_fields = ["id", "commission_rate", "card_plan_code", "card_plan_label", "installments_months"]


class PaymentSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["method", "amount", "card_type", "card_plan_label", "installments_months", "commission_rate"]
        read_only_fields = fields


class CardCommissionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = CardCommissionPlan
        fields = [
            "id",
            "code",
            "label",
            "installments_months",
            "commission_rate",
            "is_active",
            "sort_order",
        ]
        read_only_fields = fields


class SaleSerializer(serializers.ModelSerializer):
    lines = SaleLineSerializer(many=True)
    payments = PaymentSerializer(many=True)
    cashier_username = serializers.CharField(source="cashier.username", read_only=True)
    customer_summary = serializers.SerializerMethodField()
    customer_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    customer_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    override_admin_username = serializers.CharField(write_only=True, required=False, allow_blank=False)
    override_admin_password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    override_reason = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Sale
        fields = [
            "id",
            "cashier",
            "cashier_username",
            "status",
            "subtotal",
            "discount_amount",
            "total",
            "confirmed_at",
            "voided_at",
            "created_at",
            "lines",
            "payments",
            "customer_summary",
            "customer_phone",
            "customer_name",
            "override_admin_username",
            "override_admin_password",
            "override_reason",
        ]
        read_only_fields = [
            "id",
            "cashier",
            "cashier_username",
            "status",
            "subtotal",
            "discount_amount",
            "total",
            "confirmed_at",
            "voided_at",
            "created_at",
            "customer_summary",
        ]

    @staticmethod
    def _resolve_role(user):
        group_names = set(user.groups.values_list("name", flat=True))
        for role in (UserRole.ADMIN, UserRole.CASHIER, UserRole.INVESTOR):
            if role in group_names:
                return role
        return getattr(user, "role", UserRole.CASHIER)

    @staticmethod
    def _legacy_card_type_for_plan(plan):
        if plan.installments_months == 0:
            return CardType.NORMAL
        if plan.installments_months == 3:
            return CardType.MSI_3
        return None

    @staticmethod
    def _plan_from_legacy_card_type(card_type):
        if card_type == CardType.NORMAL:
            return CardCommissionPlan.objects.filter(code=CardType.NORMAL, is_active=True).first()
        if card_type == CardType.MSI_3:
            return CardCommissionPlan.objects.filter(code=CardType.MSI_3, is_active=True).first()
        return None

    def validate(self, attrs):
        request = self.context["request"]
        role = self._resolve_role(request.user)
        lines = attrs.get("lines", [])
        payments = attrs.get("payments", [])
        override_admin_username = attrs.get("override_admin_username")
        override_admin_password = attrs.get("override_admin_password")
        customer_phone = str(attrs.get("customer_phone", "")).strip()
        customer_name = str(attrs.get("customer_name", "")).strip()

        if not lines:
            raise serializers.ValidationError({"lines": "Debes incluir al menos una linea de venta."})
        if not payments:
            raise serializers.ValidationError({"payments": "Debes incluir al menos un pago."})

        subtotal = Decimal("0")
        discount_total = Decimal("0")
        needs_admin_override = False
        seen_products = set()
        for line in lines:
            if line["qty"] <= 0:
                raise serializers.ValidationError({"qty": "La cantidad debe ser mayor a 0."})
            if line["unit_price"] < 0:
                raise serializers.ValidationError({"unit_price": "El precio unitario debe ser mayor o igual a 0."})
            if line["unit_cost"] < 0:
                raise serializers.ValidationError({"unit_cost": "El costo unitario debe ser mayor o igual a 0."})
            product_id = str(line["product"].id)
            if product_id in seen_products:
                raise serializers.ValidationError({"lines": "No puedes repetir el mismo producto en varias lineas."})
            seen_products.add(product_id)
            if line.get("discount_pct", Decimal("0")) > Decimal("10.00"):
                if role == UserRole.CASHIER:
                    needs_admin_override = True
            line_amount = line["qty"] * line["unit_price"]
            line_discount = (line_amount * line["discount_pct"]) / Decimal("100")
            subtotal += line_amount
            discount_total += line_discount

        subtotal = subtotal.quantize(Decimal("0.01"))
        discount_total = discount_total.quantize(Decimal("0.01"))
        total = (subtotal - discount_total).quantize(Decimal("0.01"))
        if total < 0:
            raise serializers.ValidationError({"total": "El total no puede ser negativo."})

        override_admin_user = None
        if needs_admin_override:
            if not override_admin_username or not override_admin_password:
                raise serializers.ValidationError(
                    {"discount_pct": "Descuento mayor a 10% requiere override de admin (usuario y password)."}
                )
            override_admin_user = authenticate(username=override_admin_username, password=override_admin_password)
            if not override_admin_user or not override_admin_user.is_active:
                raise serializers.ValidationError({"override_admin_password": "Credenciales de admin invalidas."})
            override_role = self._resolve_role(override_admin_user)
            if override_role != UserRole.ADMIN:
                raise serializers.ValidationError({"override_admin_username": "El usuario override debe ser admin."})

        payments_sum = Decimal("0")
        credit_requested = Decimal("0")
        for payment in payments:
            if payment["amount"] <= 0:
                raise serializers.ValidationError({"amount": "El monto de pago debe ser mayor a 0."})
            if payment["method"] == PaymentMethod.CASH and payment.get("card_type"):
                raise serializers.ValidationError({"card_type": "No debes enviar tipo de tarjeta en pagos en efectivo."})
            if payment["method"] == PaymentMethod.CASH and payment.get("card_commission_plan"):
                raise serializers.ValidationError({"card_plan_id": "No debes enviar plan de tarjeta en pagos en efectivo."})
            if payment.get("card_type") and payment["card_type"] not in (CardType.NORMAL, CardType.MSI_3):
                raise serializers.ValidationError({"card_type": "Tipo de tarjeta invalido."})

            if payment["method"] == PaymentMethod.CARD:
                resolved_plan = payment.get("card_commission_plan")
                if not resolved_plan:
                    if not payment.get("card_type"):
                        raise serializers.ValidationError(
                            {"card_type": "El tipo de tarjeta o card_plan_id es obligatorio para pagos con tarjeta."}
                        )
                    resolved_plan = self._plan_from_legacy_card_type(payment["card_type"])
                    if not resolved_plan:
                        raise serializers.ValidationError({"card_type": "No existe un plan de comisión activo para ese tipo de tarjeta."})
                legacy_card_type = self._legacy_card_type_for_plan(resolved_plan)
                if payment.get("card_type") and legacy_card_type and payment["card_type"] != legacy_card_type:
                    raise serializers.ValidationError({"card_type": "El tipo de tarjeta no coincide con el plan seleccionado."})
                payment["card_commission_plan"] = resolved_plan
                payment["commission_rate"] = resolved_plan.commission_rate
                payment["card_plan_code"] = resolved_plan.code
                payment["card_plan_label"] = resolved_plan.label
                payment["installments_months"] = resolved_plan.installments_months
                payment["card_type"] = legacy_card_type
            else:
                payment["card_commission_plan"] = None
                payment["commission_rate"] = None
                payment["card_plan_code"] = ""
                payment["card_plan_label"] = ""
                payment["installments_months"] = 0
                payment["card_type"] = None
            if payment["method"] == PaymentMethod.CUSTOMER_CREDIT:
                if not customer_phone:
                    raise serializers.ValidationError(
                        {"customer_phone": "Debes capturar telefono del cliente para aplicar saldo a favor."}
                    )
                credit_requested += payment["amount"]
            payments_sum += payment["amount"]
        payments_sum = payments_sum.quantize(Decimal("0.01"))

        if payments_sum != total:
            raise serializers.ValidationError({"payments": "La suma de pagos debe coincidir con el total de la venta."})
        if customer_phone and not normalize_phone(customer_phone):
            raise serializers.ValidationError({"customer_phone": "El telefono es invalido."})
        if credit_requested > 0:
            customer = Customer.objects.filter(phone_normalized=normalize_phone(customer_phone)).first()
            if not customer:
                raise serializers.ValidationError({"customer_phone": "No existe un cliente con ese telefono."})
            credit = CustomerCredit.objects.filter(customer=customer).first()
            available = credit.balance if credit else Decimal("0.00")
            if credit_requested > available:
                raise serializers.ValidationError({"payments": "El saldo a favor solicitado excede el disponible."})
            attrs["_customer"] = customer
        elif customer_phone:
            attrs["_customer"] = None
        attrs["_override_admin_user"] = override_admin_user
        return attrs

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        payments = validated_data.pop("payments", [])
        customer_phone = str(validated_data.pop("customer_phone", "")).strip()
        customer_name = str(validated_data.pop("customer_name", "")).strip()
        override_admin_user = validated_data.pop("_override_admin_user", None)
        preloaded_customer = validated_data.pop("_customer", None)
        override_reason = validated_data.pop("override_reason", "")
        validated_data.pop("override_admin_username", None)
        validated_data.pop("override_admin_password", None)
        customer = None
        if customer_phone:
            customer = preloaded_customer or Customer.get_or_create_by_phone(phone=customer_phone, name=customer_name or customer_phone)
        with transaction.atomic():
            sale = Sale.objects.create(cashier=self.context["request"].user, customer=customer)

            subtotal = Decimal("0")
            discount_total = Decimal("0")
            for line in lines:
                line_obj = SaleLine.objects.create(sale=sale, **line)
                line_amount = line_obj.qty * line_obj.unit_price
                discount = (line_amount * line_obj.discount_pct) / Decimal("100")
                subtotal += line_amount
                discount_total += discount

            subtotal = subtotal.quantize(Decimal("0.01"))
            discount_total = discount_total.quantize(Decimal("0.01"))
            total = (subtotal - discount_total).quantize(Decimal("0.01"))
            for payment in payments:
                Payment.objects.create(sale=sale, **payment)

            sale.subtotal = subtotal
            sale.discount_amount = discount_total
            sale.total = total
            sale.save(update_fields=["subtotal", "discount_amount", "total"])

            if override_admin_user:
                record_audit(
                    actor=self.context["request"].user,
                    action="sale.discount_override",
                    entity_type="sale",
                    entity_id=sale.id,
                    payload={
                        "admin_user_id": str(override_admin_user.id),
                        "reason": override_reason or "",
                        "discount_amount": str(discount_total),
                    },
                )
        return sale

    def get_customer_summary(self, obj):
        customer = getattr(obj, "customer", None)
        if not customer:
            return None
        sales_qs = customer.sales.all()
        return {
            "id": str(customer.id),
            "name": customer.name,
            "phone": customer.phone,
            "sales_count": sales_qs.count(),
            "confirmed_sales_count": sales_qs.filter(status=SaleStatus.CONFIRMED).count(),
        }


class SaleListSerializer(serializers.ModelSerializer):
    payments = PaymentSummarySerializer(many=True, read_only=True)
    cashier_username = serializers.CharField(source="cashier.username", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    void_reason = serializers.SerializerMethodField()
    can_void = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = [
            "id",
            "status",
            "total",
            "created_at",
            "confirmed_at",
            "voided_at",
            "cashier",
            "cashier_username",
            "customer_name",
            "customer_phone",
            "payments",
            "void_reason",
            "can_void",
        ]
        read_only_fields = fields

    def get_void_reason(self, obj):
        void_event = getattr(obj, "void_event", None)
        return void_event.reason if void_event else None

    def get_can_void(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if obj.status != SaleStatus.CONFIRMED:
            return False

        user_role = SaleSerializer._resolve_role(user)
        if user_role == UserRole.ADMIN:
            return True
        if user_role != UserRole.CASHIER:
            return False
        if user.id != obj.cashier_id:
            return False
        if not obj.confirmed_at:
            return False

        deadline = obj.confirmed_at + timedelta(minutes=VOID_WINDOW_MINUTES)
        return timezone.now() <= deadline
