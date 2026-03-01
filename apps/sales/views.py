from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import generics, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import UserRole
from apps.audit.services import record_audit
from apps.common.permissions import RolePermission
from apps.inventory.models import InventoryMovement, MovementType
from apps.investors.models import InvestorAssignment
from apps.layaway.models import CustomerCredit, Layaway, LayawayStatus
from apps.ledger.models import LedgerEntry, LedgerEntryType
from apps.sales.models import LEGACY_CARD_TYPE_TO_RATE, CardCommissionPlan, PaymentMethod, Sale, SaleStatus, VoidEvent
from apps.sales.serializers import CardCommissionPlanSerializer, SaleListSerializer, SaleSerializer, VOID_WINDOW_MINUTES


class CardCommissionPlanListView(generics.ListAPIView):
    serializer_class = CardCommissionPlanSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "get": ["sales.view"],
    }

    def get_queryset(self):
        return CardCommissionPlan.objects.filter(is_active=True).order_by("sort_order", "installments_months", "label")


class SaleViewSet(viewsets.ModelViewSet):
    queryset = (
        Sale.objects.select_related("cashier", "void_event", "customer")
        .prefetch_related("lines", "payments__card_commission_plan")
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
                    self._apply_investor_ledger_for_line(sale, line)

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
                self._revert_investor_ledger_for_line(sale, line)

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

    def _apply_investor_ledger_for_line(self, sale, line):
        remaining_qty = line.qty
        assignments = InvestorAssignment.objects.filter(
            product=line.product, qty_assigned__gt=0
        ).order_by("created_at")

        gross_line_revenue = line.qty * line.unit_price
        line_discount = gross_line_revenue * line.discount_pct / Decimal("100")
        net_revenue = gross_line_revenue - line_discount

        commission_total = self._sale_commission_total(sale)

        for assignment in assignments:
            available = assignment.qty_assigned - assignment.qty_sold
            if available <= 0 or remaining_qty <= 0:
                continue

            consumed = min(available, remaining_qty)
            assignment.qty_sold += consumed
            assignment.save(update_fields=["qty_sold"])
            remaining_qty -= consumed

            proportional_revenue = net_revenue * (consumed / line.qty)
            proportional_cost = assignment.unit_cost * consumed
            proportional_commission = commission_total * (consumed / line.qty)

            net_profit = proportional_revenue - proportional_cost - proportional_commission
            investor_profit_share = net_profit / Decimal("2")

            LedgerEntry.objects.create(
                investor=assignment.investor,
                entry_type=LedgerEntryType.INVENTORY_TO_CAPITAL,
                capital_delta=proportional_cost,
                inventory_delta=-proportional_cost,
                profit_delta=Decimal("0"),
                reference_type="sale",
                reference_id=str(sale.id),
                note="Capital recovery",
            )
            LedgerEntry.objects.create(
                investor=assignment.investor,
                entry_type=LedgerEntryType.PROFIT_SHARE,
                capital_delta=Decimal("0"),
                inventory_delta=Decimal("0"),
                profit_delta=investor_profit_share,
                reference_type="sale",
                reference_id=str(sale.id),
                note="Profit share 50/50",
            )

    def _revert_investor_ledger_for_line(self, sale, line):
        remaining_qty = line.qty
        assignments = InvestorAssignment.objects.filter(
            product=line.product,
            qty_sold__gt=0,
        ).order_by("-created_at")

        gross_line_revenue = line.qty * line.unit_price
        line_discount = gross_line_revenue * line.discount_pct / Decimal("100")
        net_revenue = gross_line_revenue - line_discount
        commission_total = self._sale_commission_total(sale)

        for assignment in assignments:
            if remaining_qty <= 0:
                break

            reversible_qty = min(assignment.qty_sold, remaining_qty)
            if reversible_qty <= 0:
                continue

            proportional_revenue = net_revenue * (reversible_qty / line.qty)
            proportional_cost = assignment.unit_cost * reversible_qty
            proportional_commission = commission_total * (reversible_qty / line.qty)
            net_profit = proportional_revenue - proportional_cost - proportional_commission
            investor_profit_share = net_profit / Decimal("2")

            assignment.qty_sold -= reversible_qty
            assignment.save(update_fields=["qty_sold"])
            remaining_qty -= reversible_qty

            LedgerEntry.objects.create(
                investor=assignment.investor,
                entry_type=LedgerEntryType.INVENTORY_TO_CAPITAL,
                capital_delta=-proportional_cost,
                inventory_delta=proportional_cost,
                profit_delta=Decimal("0"),
                reference_type="sale_void",
                reference_id=str(sale.id),
                note="Capital recovery reversal (void)",
            )
            LedgerEntry.objects.create(
                investor=assignment.investor,
                entry_type=LedgerEntryType.PROFIT_SHARE,
                capital_delta=Decimal("0"),
                inventory_delta=Decimal("0"),
                profit_delta=-investor_profit_share,
                reference_type="sale_void",
                reference_id=str(sale.id),
                note="Profit share reversal (void)",
            )

    @staticmethod
    def _sale_commission_total(sale):
        commission_total = Decimal("0")
        for payment in sale.payments.all():
            if payment.method != PaymentMethod.CARD:
                continue
            commission_rate = payment.commission_rate
            if commission_rate is None:
                commission_rate = LEGACY_CARD_TYPE_TO_RATE.get(payment.card_type, Decimal("0"))
            commission_total += payment.amount * commission_rate
        return commission_total

    @staticmethod
    def _apply_customer_credit_if_needed(sale):
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
