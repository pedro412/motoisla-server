from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.response import Response

from apps.audit.services import record_audit
from apps.catalog.models import Product
from apps.catalog.querysets import with_inventory_metrics
from apps.common.permissions import RolePermission
from apps.investors.models import Investor, InvestorAssignment
from apps.investors.serializers import (
    InvestorAmountSerializer,
    InvestorAssignmentSerializer,
    InvestorPurchaseSerializer,
    InvestorSerializer,
    LedgerEntrySerializer,
)
from apps.ledger.models import LedgerEntry, LedgerEntryType
from apps.ledger.services import (
    create_capital_deposit,
    create_capital_withdrawal,
    create_reinvestment,
    current_balances,
)


class InvestorViewSet(viewsets.ModelViewSet):
    queryset = Investor.objects.select_related("user")
    serializer_class = InvestorSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["investor.manage"],
        "retrieve": ["investor.manage"],
        "create": ["investor.manage"],
        "partial_update": ["investor.manage"],
        "update": ["investor.manage"],
        "destroy": ["investor.manage"],
        "deposit": ["ledger.manage"],
        "withdraw": ["ledger.manage"],
        "reinvest": ["ledger.manage"],
        "ledger": ["ledger.manage"],
        "purchases": ["investor.manage"],
    }

    def get_queryset(self):
        queryset = Investor.objects.select_related("user").annotate(
            balance_capital=Coalesce(
                Sum("ledger_entries__capital_delta"),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
            balance_inventory=Coalesce(
                Sum("ledger_entries__inventory_delta"),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
            balance_profit=Coalesce(
                Sum("ledger_entries__profit_delta"),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
        )
        query = self.request.query_params.get("q")
        if query:
            queryset = queryset.filter(Q(display_name__icontains=query.strip()))
        return queryset.order_by("display_name")

    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        investor = self.get_object()
        entries = LedgerEntry.objects.filter(investor=investor).order_by("-created_at")
        page = self.paginate_queryset(entries)
        if page is not None:
            serializer = LedgerEntrySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = LedgerEntrySerializer(entries, many=True)
        return Response({"count": len(serializer.data), "next": None, "previous": None, "results": serializer.data})

    @action(detail=True, methods=["post"])
    def deposit(self, request, pk=None):
        investor = self.get_object()
        serializer = InvestorAmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        entry = create_capital_deposit(
            investor=investor,
            amount=serializer.validated_data["amount"],
            reference_type="manual_deposit",
            reference_id=str(investor.id),
            note=serializer.validated_data.get("note", ""),
        )
        record_audit(
            actor=request.user,
            action="investor.deposit",
            entity_type="investor",
            entity_id=investor.id,
            payload={"entry_id": str(entry.id), "amount": str(serializer.validated_data['amount'])},
        )
        return Response(LedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        investor = self.get_object()
        serializer = InvestorAmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            entry = create_capital_withdrawal(
                investor=investor,
                amount=serializer.validated_data["amount"],
                reference_type="manual_withdrawal",
                reference_id=str(investor.id),
                note=serializer.validated_data.get("note", ""),
            )
        except ValueError as exc:
            return Response({"code": "invalid_withdrawal", "detail": str(exc), "fields": {}}, status=400)

        record_audit(
            actor=request.user,
            action="investor.withdraw",
            entity_type="investor",
            entity_id=investor.id,
            payload={"entry_id": str(entry.id), "amount": str(serializer.validated_data['amount'])},
        )
        return Response(LedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def reinvest(self, request, pk=None):
        investor = self.get_object()
        serializer = InvestorAmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            create_reinvestment(
                investor=investor,
                amount=serializer.validated_data["amount"],
                reference_type="manual_reinvestment",
                reference_id=str(investor.id),
                note=serializer.validated_data.get("note", ""),
            )
        except ValueError as exc:
            return Response({"code": "invalid_reinvestment", "detail": str(exc), "fields": {}}, status=400)

        record_audit(
            actor=request.user,
            action="investor.reinvest",
            entity_type="investor",
            entity_id=investor.id,
            payload={"amount": str(serializer.validated_data['amount'])},
        )
        balances = current_balances(investor)
        return Response({"investor_id": str(investor.id), "balances": balances}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="purchases")
    def purchases(self, request, pk=None):
        investor = self.get_object()
        serializer = InvestorPurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            locked_investor = Investor.objects.select_for_update().get(pk=investor.pk)
            raw_lines = serializer.validated_data["lines"]
            lines_by_tuple = {}
            requested_qty_by_product = defaultdict(lambda: Decimal("0.00"))

            for line in raw_lines:
                tuple_key = (str(line["product"].id), line["unit_cost_gross"])
                if tuple_key in lines_by_tuple:
                    lines_by_tuple[tuple_key]["qty"] += line["qty"]
                else:
                    lines_by_tuple[tuple_key] = {
                        "product": line["product"],
                        "qty": line["qty"],
                        "unit_cost_gross": line["unit_cost_gross"],
                    }

            lines = list(lines_by_tuple.values())

            for line in lines:
                requested_qty_by_product[str(line["product"].id)] += line["qty"]

            product_ids = list(requested_qty_by_product.keys())
            products = with_inventory_metrics(Product.objects.filter(id__in=product_ids))
            products_by_id = {str(product.id): product for product in products}
            line_errors: dict[str, str] = {}

            for product_id, requested_qty in requested_qty_by_product.items():
                product = products_by_id.get(product_id)
                if product is None:
                    line_errors[product_id] = "Producto no encontrado."
                    continue
                if not product.is_active:
                    line_errors[product_id] = f"{product.name} está inactivo."
                    continue

                assignable_qty = product.stock - getattr(product, "investor_reserved_qty", Decimal("0.00"))
                if assignable_qty < 0:
                    assignable_qty = Decimal("0.00")
                if requested_qty > assignable_qty:
                    line_errors[product_id] = (
                        f"{product.name} solo tiene {assignable_qty:.2f} unidades disponibles para inversionistas."
                    )

            if line_errors:
                raise serializers.ValidationError(
                    {
                        "detail": "No fue posible completar la compra del inversionista.",
                        "lines": line_errors,
                    }
                )

            purchase_total = sum(line["qty"] * line["unit_cost_gross"] for line in lines)
            balances = current_balances(locked_investor)
            if purchase_total > balances["capital"]:
                raise serializers.ValidationError(
                    {
                        "detail": "No hay capital liquido suficiente para completar la compra.",
                        "capital": ["El total de la compra excede el capital disponible."],
                    }
                )

            created_assignments = []
            created_entries = []

            for line in lines:
                product = products_by_id[str(line["product"].id)]
                assignment = InvestorAssignment.objects.create(
                    investor=locked_investor,
                    product=product,
                    qty_assigned=line["qty"],
                    unit_cost=line["unit_cost_gross"],
                )
                created_assignments.append(assignment)

                line_total = line["qty"] * line["unit_cost_gross"]
                entry = LedgerEntry.objects.create(
                    investor=locked_investor,
                    entry_type=LedgerEntryType.CAPITAL_TO_INVENTORY,
                    capital_delta=-line_total,
                    inventory_delta=line_total,
                    profit_delta=Decimal("0.00"),
                    reference_type="investor_assignment",
                    reference_id=str(assignment.id),
                    note=f"Investor purchase {product.sku}",
                )
                created_entries.append(entry)

                record_audit(
                    actor=request.user,
                    action="investor.assignment.create",
                    entity_type="investor_assignment",
                    entity_id=assignment.id,
                    payload={
                        "investor_id": str(assignment.investor_id),
                        "product_id": str(assignment.product_id),
                        "qty_assigned": str(assignment.qty_assigned),
                        "unit_cost": str(assignment.unit_cost),
                        "tax_rate_pct": str(serializer.validated_data["tax_rate_pct"]),
                    },
                )

            balances = current_balances(locked_investor)

        return Response(
            {
                "investor_id": str(locked_investor.id),
                "purchase_total": f"{purchase_total:.2f}",
                "balances": balances,
                "assignments": InvestorAssignmentSerializer(created_assignments, many=True).data,
                "ledger_entries": LedgerEntrySerializer(created_entries, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class InvestorAssignmentViewSet(viewsets.ModelViewSet):
    queryset = InvestorAssignment.objects.select_related("investor", "product")
    serializer_class = InvestorAssignmentSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["investor.manage"],
        "retrieve": ["investor.manage"],
        "create": ["investor.manage"],
        "partial_update": ["investor.manage"],
        "update": ["investor.manage"],
        "destroy": ["investor.manage"],
    }

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .annotate(qty_available=F("qty_assigned") - F("qty_sold"))
            .select_related("investor", "product")
            .order_by("-created_at")
        )
        investor_id = self.request.query_params.get("investor")
        if investor_id:
            queryset = queryset.filter(investor_id=investor_id)
        return queryset

    def perform_create(self, serializer):
        assignment = serializer.save()
        record_audit(
            actor=self.request.user,
            action="investor.assignment.create",
            entity_type="investor_assignment",
            entity_id=assignment.id,
            payload={
                "investor_id": str(assignment.investor_id),
                "product_id": str(assignment.product_id),
                "qty_assigned": str(assignment.qty_assigned),
                "unit_cost": str(assignment.unit_cost),
            },
        )

    def perform_update(self, serializer):
        assignment = self.get_object()
        before = {
            "qty_assigned": str(assignment.qty_assigned),
            "qty_sold": str(assignment.qty_sold),
            "unit_cost": str(assignment.unit_cost),
        }
        assignment = serializer.save()
        after = {
            "qty_assigned": str(assignment.qty_assigned),
            "qty_sold": str(assignment.qty_sold),
            "unit_cost": str(assignment.unit_cost),
        }
        record_audit(
            actor=self.request.user,
            action="investor.assignment.update",
            entity_type="investor_assignment",
            entity_id=assignment.id,
            payload={"before": before, "after": after},
        )

    def perform_destroy(self, instance):
        record_audit(
            actor=self.request.user,
            action="investor.assignment.delete",
            entity_type="investor_assignment",
            entity_id=instance.id,
            payload={
                "investor_id": str(instance.investor_id),
                "product_id": str(instance.product_id),
                "qty_assigned": str(instance.qty_assigned),
                "qty_sold": str(instance.qty_sold),
                "unit_cost": str(instance.unit_cost),
            },
        )
        super().perform_destroy(instance)


class MyInvestorProfileView(GenericAPIView):
    permission_classes = [RolePermission]
    capability_map = {"get": ["investor.view.own"]}

    def get(self, request, *args, **kwargs):
        investor = Investor.objects.filter(user=request.user).first()
        if investor is None:
            return Response(
                {"code": "investor_profile_not_found", "detail": "No existe perfil de inversionista para este usuario.", "fields": {}},
                status=404,
            )
        payload = InvestorSerializer(investor).data
        return Response(payload)


class MyLedgerView(ListAPIView):
    permission_classes = [RolePermission]
    capability_map = {"get": ["ledger.view.own"]}
    serializer_class = LedgerEntrySerializer

    def get_queryset(self):
        investor = Investor.objects.filter(user=self.request.user).first()
        if investor is None:
            return LedgerEntry.objects.none()
        return LedgerEntry.objects.filter(investor=investor)
