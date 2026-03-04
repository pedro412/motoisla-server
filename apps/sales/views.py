from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import generics, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import UserRole
from apps.audit.services import record_audit
from apps.common.permissions import RolePermission
from apps.inventory.models import InventoryMovement, MovementType
from apps.layaway.models import CustomerCredit, Layaway, LayawayStatus
from apps.sales.models import CardCommissionPlan, PaymentMethod, Sale, SaleStatus, VoidEvent
from apps.sales.profitability import (
    apply_sale_profitability,
    build_sale_profitability_preview,
    current_operating_cost_rate_snapshot,
    revert_sale_profitability,
)
from apps.sales.serializers import (
    CardCommissionPlanSerializer,
    OperatingCostRateSerializer,
    SaleListSerializer,
    SaleProfitabilityPreviewSerializer,
    SaleSerializer,
    VOID_WINDOW_MINUTES,
)


class CardCommissionPlanListView(generics.ListAPIView):
    serializer_class = CardCommissionPlanSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "get": ["sales.view"],
    }

    def get_queryset(self):
        return CardCommissionPlan.objects.filter(is_active=True).order_by("sort_order", "installments_months", "label")


class SaleProfitabilityPreviewView(generics.GenericAPIView):
    serializer_class = SaleProfitabilityPreviewSerializer
    permission_classes = [RolePermission]
    capability_map = {"post": ["sales.create"]}

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preview = build_sale_profitability_preview(
            lines=serializer.validated_data["lines"],
            payments=serializer.validated_data["payments"],
        )
        return Response(preview, status=200)


class OperatingCostRateView(generics.GenericAPIView):
    serializer_class = OperatingCostRateSerializer
    permission_classes = [RolePermission]
    capability_map = {"get": ["sales.create"]}

    def get(self, request, *args, **kwargs):
        snapshot = current_operating_cost_rate_snapshot()
        payload = {
            "operating_cost_rate": snapshot.operating_cost_rate,
            "rate_source": snapshot.rate_source,
            "calculated_at": snapshot.calculated_at,
        }
        return Response(self.get_serializer(payload).data, status=200)


class SaleViewSet(viewsets.ModelViewSet):
    queryset = (
        Sale.objects.select_related("cashier", "void_event", "customer")
        .prefetch_related(
            "lines",
            "payments__card_commission_plan",
            "profitability_snapshot__lines__investor",
            "profitability_snapshot__lines__product",
        )
        .order_by("-created_at")
    )
    serializer_class = SaleSerializer
    permission_classes = [RolePermission]
    http_method_names = ["get", "post", "head", "options"]
    capability_map = {
        "list": ["sales.view"],
        "retrieve": ["sales.view"],
        "create": ["sales.create"],
        "confirm": ["sales.confirm"],
        "void": ["sales.void.own_window"],
    }

    def get_serializer_class(self):
        if self.action == "list":
            return SaleListSerializer
        return SaleSerializer

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        sale = self.get_object()
        if sale.status == SaleStatus.CONFIRMED:
            return Response({"code": "already_confirmed", "detail": "La venta ya estaba confirmada.", "fields": {}}, status=200)
        if sale.status == SaleStatus.VOID:
            return Response({"code": "invalid_state", "detail": "No puedes confirmar una venta cancelada.", "fields": {}}, status=400)

        try:
            with transaction.atomic():
                self._apply_customer_credit_if_needed(sale)
                for line in sale.lines.all():
                    InventoryMovement.objects.create(
                        product=line.product,
                        movement_type=MovementType.OUTBOUND,
                        quantity_delta=-line.qty,
                        reference_type="sale_confirm",
                        reference_id=str(sale.id),
                        note="Sale confirmation",
                        created_by=request.user,
                    )
                apply_sale_profitability(sale=sale)

                sale.status = SaleStatus.CONFIRMED
                sale.confirmed_at = timezone.now()
                sale.save(update_fields=["status", "confirmed_at"])

                if sale.discount_amount > 0:
                    record_audit(
                        actor=request.user,
                        action="sale.discount",
                        entity_type="sale",
                        entity_id=sale.id,
                        payload={"discount_amount": str(sale.discount_amount)},
                    )

                record_audit(
                    actor=request.user,
                    action="sale.confirm",
                    entity_type="sale",
                    entity_id=sale.id,
                    payload={"total": str(sale.total)},
                )
        except ValueError as exc:
            return Response({"code": "invalid_payment", "detail": str(exc), "fields": {}}, status=400)

        return Response(self.get_serializer(sale).data, status=200)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        sale = self.get_object()
        if sale.status != SaleStatus.CONFIRMED:
            return Response(
                {"code": "invalid_state", "detail": "Solo puedes anular ventas confirmadas.", "fields": {}},
                status=400,
            )

        user_role = self._resolve_role(request.user)
        if user_role == UserRole.CASHIER:
            deadline = sale.confirmed_at + timedelta(minutes=VOID_WINDOW_MINUTES)
            if request.user.id != sale.cashier_id:
                return Response(
                    {"code": "forbidden", "detail": "Cajero solo puede anular sus propias ventas.", "fields": {}},
                    status=403,
                )
            if timezone.now() > deadline:
                return Response(
                    {"code": "forbidden", "detail": "La ventana de anulacion (10 min) ya expiro.", "fields": {}},
                    status=403,
                )

        reason = request.data.get("reason", "Sin motivo")

        with transaction.atomic():
            self._restore_customer_credit_if_needed(sale)
            for line in sale.lines.all():
                InventoryMovement.objects.create(
                    product=line.product,
                    movement_type=MovementType.INBOUND,
                    quantity_delta=line.qty,
                    reference_type="sale_void",
                    reference_id=str(sale.id),
                    note="Sale void",
                    created_by=request.user,
                )
            revert_sale_profitability(sale=sale)

            self._mark_layaway_refunded_if_linked(sale, request.user)

            sale.status = SaleStatus.VOID
            sale.voided_at = timezone.now()
            sale.save(update_fields=["status", "voided_at"])
            VoidEvent.objects.create(sale=sale, reason=reason, actor=request.user)

            record_audit(
                actor=request.user,
                action="sale.void",
                entity_type="sale",
                entity_id=sale.id,
                payload={"reason": reason},
            )

        return Response(self.get_serializer(sale).data, status=200)

    @staticmethod
    def _apply_customer_credit_if_needed(sale):
        from decimal import Decimal

        credit_amount = sum(
            (payment.amount for payment in sale.payments.all() if payment.method == PaymentMethod.CUSTOMER_CREDIT),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))
        if credit_amount <= 0:
            return
        if not sale.customer_id:
            raise ValueError("La venta no tiene cliente asociado para aplicar saldo a favor.")
        credit = CustomerCredit.objects.select_for_update().filter(customer=sale.customer).first()
        available = credit.balance if credit else Decimal("0.00")
        if credit_amount > available:
            raise ValueError("El saldo a favor del cliente ya no es suficiente para confirmar la venta.")
        credit.balance = (credit.balance - credit_amount).quantize(Decimal("0.01"))
        credit.save(update_fields=["balance", "updated_at", "customer_name", "customer_phone"])

    @staticmethod
    def _restore_customer_credit_if_needed(sale):
        from decimal import Decimal

        credit_amount = sum(
            (payment.amount for payment in sale.payments.all() if payment.method == PaymentMethod.CUSTOMER_CREDIT),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))
        if credit_amount <= 0 or not sale.customer_id:
            return
        credit = CustomerCredit.objects.select_for_update().filter(customer=sale.customer).first()
        if not credit:
            credit = CustomerCredit.objects.create(
                customer=sale.customer,
                customer_name=sale.customer.name,
                customer_phone=sale.customer.phone,
                balance=Decimal("0.00"),
            )
        credit.balance = (credit.balance + credit_amount).quantize(Decimal("0.01"))
        credit.save(update_fields=["balance", "updated_at", "customer_name", "customer_phone"])

    @staticmethod
    def _mark_layaway_refunded_if_linked(sale, user):
        layaway = Layaway.objects.select_for_update().filter(settled_sale_id=sale.id).first()
        if not layaway or layaway.status != LayawayStatus.SETTLED:
            return
        layaway.status = LayawayStatus.REFUNDED
        layaway.save(update_fields=["status", "updated_at"])
        record_audit(
            actor=user,
            action="layaway.refund",
            entity_type="layaway",
            entity_id=layaway.id,
            payload={"sale_id": str(sale.id)},
        )

    @staticmethod
    def _resolve_role(user):
        group_names = set(user.groups.values_list("name", flat=True))
        for role in (UserRole.ADMIN, UserRole.CASHIER, UserRole.INVESTOR):
            if role in group_names:
                return role
        return getattr(user, "role", UserRole.CASHIER)
