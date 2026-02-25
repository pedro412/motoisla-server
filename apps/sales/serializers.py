from decimal import Decimal

from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.accounts.models import UserRole
from apps.audit.services import record_audit
from apps.sales.models import CardType, Payment, PaymentMethod, Sale, SaleLine


class SaleLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleLine
        fields = ["id", "product", "qty", "unit_price", "unit_cost", "discount_pct"]
        read_only_fields = ["id"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "method", "amount", "card_type"]
        read_only_fields = ["id"]


class SaleSerializer(serializers.ModelSerializer):
    lines = SaleLineSerializer(many=True)
    payments = PaymentSerializer(many=True)
    override_admin_username = serializers.CharField(write_only=True, required=False, allow_blank=False)
    override_admin_password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    override_reason = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Sale
        fields = [
            "id",
            "cashier",
            "status",
            "subtotal",
            "discount_amount",
            "total",
            "confirmed_at",
            "voided_at",
            "created_at",
            "lines",
            "payments",
            "override_admin_username",
            "override_admin_password",
            "override_reason",
        ]
        read_only_fields = [
            "id",
            "cashier",
            "status",
            "subtotal",
            "discount_amount",
            "total",
            "confirmed_at",
            "voided_at",
            "created_at",
        ]

    @staticmethod
    def _resolve_role(user):
        group_names = set(user.groups.values_list("name", flat=True))
        for role in (UserRole.ADMIN, UserRole.CASHIER, UserRole.INVESTOR):
            if role in group_names:
                return role
        return getattr(user, "role", UserRole.CASHIER)

    def validate(self, attrs):
        request = self.context["request"]
        role = self._resolve_role(request.user)
        lines = attrs.get("lines", [])
        payments = attrs.get("payments", [])
        override_admin_username = attrs.get("override_admin_username")
        override_admin_password = attrs.get("override_admin_password")

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
        for payment in payments:
            if payment["amount"] <= 0:
                raise serializers.ValidationError({"amount": "El monto de pago debe ser mayor a 0."})
            if payment["method"] == PaymentMethod.CARD and not payment.get("card_type"):
                raise serializers.ValidationError({"card_type": "El tipo de tarjeta es obligatorio para pagos con tarjeta."})
            if payment["method"] == PaymentMethod.CASH and payment.get("card_type"):
                raise serializers.ValidationError({"card_type": "No debes enviar tipo de tarjeta en pagos en efectivo."})
            if payment.get("card_type") and payment["card_type"] not in (CardType.NORMAL, CardType.MSI_3):
                raise serializers.ValidationError({"card_type": "Tipo de tarjeta invalido."})
            payments_sum += payment["amount"]
        payments_sum = payments_sum.quantize(Decimal("0.01"))

        if payments_sum != total:
            raise serializers.ValidationError({"payments": "La suma de pagos debe coincidir con el total de la venta."})
        attrs["_override_admin_user"] = override_admin_user
        return attrs

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        payments = validated_data.pop("payments", [])
        override_admin_user = validated_data.pop("_override_admin_user", None)
        override_reason = validated_data.pop("override_reason", "")
        validated_data.pop("override_admin_username", None)
        validated_data.pop("override_admin_password", None)
        sale = Sale.objects.create(cashier=self.context["request"].user)

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
