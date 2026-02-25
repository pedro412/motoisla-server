from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import UserRole
from apps.audit.services import record_audit
from apps.common.permissions import RolePermission
from apps.inventory.models import InventoryMovement, MovementType
from apps.layaway.models import CustomerCredit, Layaway, LayawayPayment, LayawayStatus
from apps.layaway.serializers import CustomerCreditSerializer, LayawaySerializer
from apps.sales.models import Sale, SaleLine, Payment, PaymentMethod, SaleStatus


class LayawayViewSet(viewsets.ModelViewSet):
    queryset = Layaway.objects.select_related("product", "created_by")
    serializer_class = LayawaySerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["layaway.manage"],
        "retrieve": ["layaway.manage"],
        "create": ["layaway.manage"],
        "settle": ["layaway.manage"],
        "expire": ["layaway.manage"],
    }

    @staticmethod
    def _resolve_role(user):
        group_names = set(user.groups.values_list("name", flat=True))
        for role in (UserRole.ADMIN, UserRole.CASHIER, UserRole.INVESTOR):
            if role in group_names:
                return role
        return getattr(user, "role", UserRole.CASHIER)

    def perform_create(self, serializer):
        with transaction.atomic():
            layaway = serializer.save()
            InventoryMovement.objects.create(
                product=layaway.product,
                movement_type=MovementType.RESERVED,
                quantity_delta=-layaway.qty,
                reference_type="layaway_reserve",
                reference_id=str(layaway.id),
                note="Layaway reserve",
                created_by=self.request.user,
            )
            LayawayPayment.objects.create(layaway=layaway, amount=layaway.deposit_amount)
            record_audit(
                actor=self.request.user,
                action="layaway.create",
                entity_type="layaway",
                entity_id=layaway.id,
                payload={"deposit": str(layaway.deposit_amount)},
            )

    @action(detail=True, methods=["post"])
    def settle(self, request, pk=None):
        layaway = self.get_object()
        if layaway.status != LayawayStatus.ACTIVE:
            return Response({"code": "invalid_state", "detail": "El apartado no esta activo.", "fields": {}}, status=400)

        amount = Decimal(str(request.data.get("amount", "0"))).quantize(Decimal("0.01"))
        credit_to_apply = Decimal(str(request.data.get("credit_amount", "0"))).quantize(Decimal("0.01"))
        if amount < 0:
            return Response({"code": "invalid_payment", "detail": "El monto en efectivo no puede ser negativo.", "fields": {}}, status=400)
        if credit_to_apply < 0:
            return Response({"code": "invalid_payment", "detail": "El saldo a favor a aplicar no puede ser negativo.", "fields": {}}, status=400)

        paid_total = sum((payment.amount for payment in layaway.payments.all()), Decimal("0"))
        due = (layaway.total_price - paid_total).quantize(Decimal("0.01"))
        if due <= 0:
            return Response({"code": "invalid_state", "detail": "El apartado ya no tiene saldo pendiente.", "fields": {}}, status=400)

        credit = CustomerCredit.objects.filter(
            customer_name=layaway.customer_name,
            customer_phone=layaway.customer_phone,
        ).first()
        available_credit = credit.balance.quantize(Decimal("0.01")) if credit else Decimal("0.00")
        if credit_to_apply > available_credit:
            return Response(
                {"code": "invalid_payment", "detail": "El saldo a favor solicitado excede el disponible.", "fields": {}},
                status=400,
            )
        if credit_to_apply > due:
            return Response(
                {"code": "invalid_payment", "detail": "El saldo a favor aplicado no puede exceder el saldo pendiente.", "fields": {}},
                status=400,
            )

        remaining_due = (due - credit_to_apply).quantize(Decimal("0.01"))
        if amount != remaining_due:
            return Response(
                {
                    "code": "invalid_payment",
                    "detail": "El monto en efectivo debe coincidir exactamente con el saldo restante.",
                    "fields": {"remaining_due": str(remaining_due)},
                },
                status=400,
            )

        with transaction.atomic():
            if credit_to_apply > 0:
                credit.balance = (credit.balance - credit_to_apply).quantize(Decimal("0.01"))
                credit.save(update_fields=["balance", "updated_at"])

            settlement_amount = (amount + credit_to_apply).quantize(Decimal("0.01"))
            LayawayPayment.objects.create(layaway=layaway, amount=settlement_amount)
            layaway.status = LayawayStatus.SETTLED
            layaway.save(update_fields=["status"])

            sale = Sale.objects.create(
                cashier=request.user,
                status=SaleStatus.CONFIRMED,
                subtotal=layaway.total_price,
                discount_amount=Decimal("0"),
                total=layaway.total_price,
                confirmed_at=timezone.now(),
            )
            SaleLine.objects.create(
                sale=sale,
                product=layaway.product,
                qty=layaway.qty,
                unit_price=layaway.total_price / layaway.qty,
                unit_cost=Decimal("0"),
                discount_pct=Decimal("0"),
            )
            Payment.objects.create(sale=sale, method=PaymentMethod.CASH, amount=layaway.total_price)

            record_audit(
                actor=request.user,
                action="layaway.settle",
                entity_type="layaway",
                entity_id=layaway.id,
                payload={
                    "sale_id": str(sale.id),
                    "cash_paid": str(amount),
                    "credit_applied": str(credit_to_apply),
                },
            )

        return Response(self.get_serializer(layaway).data, status=200)

    @action(detail=True, methods=["post"])
    def expire(self, request, pk=None):
        layaway = self.get_object()
        if layaway.status != LayawayStatus.ACTIVE:
            return Response({"code": "invalid_state", "detail": "El apartado no esta activo.", "fields": {}}, status=400)

        user_role = self._resolve_role(request.user)
        force = str(request.data.get("force", "false")).lower() in {"1", "true", "yes"}
        if timezone.now() < layaway.expires_at and not (force and user_role == UserRole.ADMIN):
            return Response(
                {"code": "invalid_state", "detail": "El apartado aun no vence. Solo admin puede forzar vencimiento.", "fields": {}},
                status=400,
            )

        with transaction.atomic():
            layaway.status = LayawayStatus.EXPIRED
            layaway.save(update_fields=["status"])

            InventoryMovement.objects.create(
                product=layaway.product,
                movement_type=MovementType.RELEASED,
                quantity_delta=layaway.qty,
                reference_type="layaway_expire",
                reference_id=str(layaway.id),
                note="Layaway expired release",
                created_by=request.user,
            )

            credit, _ = CustomerCredit.objects.get_or_create(
                customer_name=layaway.customer_name,
                customer_phone=layaway.customer_phone,
                defaults={"balance": Decimal("0")},
            )
            credit.balance += layaway.deposit_amount
            credit.save(update_fields=["balance", "updated_at"])

            record_audit(
                actor=request.user,
                action="layaway.expire",
                entity_type="layaway",
                entity_id=layaway.id,
                payload={"credit_added": str(layaway.deposit_amount)},
            )

        return Response(self.get_serializer(layaway).data, status=200)


class CustomerCreditViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CustomerCredit.objects.all()
    serializer_class = CustomerCreditSerializer
    permission_classes = [RolePermission]
    capability_map = {"list": ["layaway.manage"], "retrieve": ["layaway.manage"], "apply": ["layaway.manage"]}

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        credit = self.get_object()
        amount = Decimal(str(request.data.get("amount", "0"))).quantize(Decimal("0.01"))
        reference_type = str(request.data.get("reference_type", "manual")).strip() or "manual"
        reference_id = str(request.data.get("reference_id", "")).strip() or "-"

        if amount <= 0:
            return Response(
                {"code": "invalid_payment", "detail": "El monto a aplicar debe ser mayor a 0.", "fields": {}},
                status=400,
            )
        if amount > credit.balance:
            return Response(
                {"code": "invalid_payment", "detail": "El monto a aplicar excede el saldo disponible.", "fields": {}},
                status=400,
            )

        with transaction.atomic():
            credit.balance = (credit.balance - amount).quantize(Decimal("0.01"))
            credit.save(update_fields=["balance", "updated_at"])
            record_audit(
                actor=request.user,
                action="customer_credit.apply",
                entity_type="customer_credit",
                entity_id=credit.id,
                payload={"amount": str(amount), "reference_type": reference_type, "reference_id": reference_id},
            )
        return Response(self.get_serializer(credit).data, status=200)
