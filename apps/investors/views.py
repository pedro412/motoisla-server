from django.db.models import F
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.response import Response

from apps.audit.services import record_audit
from apps.common.permissions import RolePermission
from apps.investors.models import Investor, InvestorAssignment
from apps.investors.serializers import (
    InvestorAmountSerializer,
    InvestorAssignmentSerializer,
    InvestorSerializer,
    LedgerEntrySerializer,
)
from apps.ledger.models import LedgerEntry
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
        "deposit": ["ledger.manage"],
        "withdraw": ["ledger.manage"],
        "reinvest": ["ledger.manage"],
        "ledger": ["ledger.manage"],
    }

    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        investor = self.get_object()
        entries = LedgerEntry.objects.filter(investor=investor).order_by("-created_at")
        serializer = LedgerEntrySerializer(entries, many=True)
        return Response({"count": len(serializer.data), "results": serializer.data})

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
    }

    def get_queryset(self):
        return super().get_queryset().annotate(qty_available=F("qty_assigned") - F("qty_sold"))


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
        balances = current_balances(investor)
        payload = InvestorSerializer(investor).data
        payload["balances"] = balances
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
