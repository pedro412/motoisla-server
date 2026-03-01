from decimal import Decimal

from django.db import models, transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import UserRole
from apps.audit.services import record_audit
from apps.common.permissions import RolePermission
from apps.inventory.models import InventoryMovement, MovementType
from apps.investors.models import InvestorAssignment
from apps.ledger.models import LedgerEntry, LedgerEntryType
from apps.layaway.models import (
    Customer,
    CustomerCredit,
    Layaway,
    LayawayExtensionLog,
    LayawayLine,
    LayawayPayment,
    LayawayStatus,
    normalize_phone,
)
from apps.layaway.serializers import (
    CustomerCreditSerializer,
    CustomerSerializer,
    LayawayCreateSerializer,
    LayawayExtendSerializer,
    LayawayPaymentCreateSerializer,
    LayawaySerializer,
)
from apps.sales.models import Payment, PaymentMethod, Sale, SaleLine, SaleStatus


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.order_by("-updated_at")
    serializer_class = CustomerSerializer
    permission_classes = [RolePermission]
    http_method_names = ["get", "post", "head", "options"]
    capability_map = {"list": ["layaway.manage"], "retrieve": ["layaway.manage"], "create": ["layaway.manage"]}

    def get_queryset(self):
        queryset = super().get_queryset()
        phone = self.request.query_params.get("phone")
        query = self.request.query_params.get("q")
        if phone:
            queryset = queryset.filter(phone_normalized=normalize_phone(phone))
        if query:
            normalized = normalize_phone(query)
            queryset = queryset.filter(Q(name__icontains=query) | Q(phone__icontains=query) | Q(phone_normalized__icontains=normalized))
        return queryset

    def create(self, request, *args, **kwargs):
        phone = str(request.data.get("phone", "")).strip()
        name = str(request.data.get("name", "")).strip()
        notes = str(request.data.get("notes", "")).strip()
        if not phone or not name:
            return Response({"code": "invalid_customer", "detail": "Nombre y telefono son obligatorios.", "fields": {}}, status=400)
        customer = Customer.get_or_create_by_phone(phone=phone, name=name, notes=notes)
        serializer = self.get_serializer(customer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class LayawayViewSet(viewsets.ModelViewSet):
    queryset = (
        Layaway.objects.select_related("product", "created_by", "customer")
        .prefetch_related(
            Prefetch("lines", queryset=LayawayLine.objects.select_related("product")),
            "payments",
            "extensions__created_by",
        )
        .order_by(
            models.Case(
                models.When(status=LayawayStatus.EXPIRED, then=0),
                models.When(status=LayawayStatus.ACTIVE, then=1),
                models.When(status=LayawayStatus.REFUNDED, then=2),
                default=3,
                output_field=models.IntegerField(),
            ),
            "expires_at",
            "-created_at",
        )
    )
    serializer_class = LayawaySerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["layaway.manage"],
        "retrieve": ["layaway.manage"],
        "create": ["layaway.manage"],
        "payments": ["layaway.manage"],
        "settle": ["layaway.manage"],
        "extend": ["layaway.manage"],
        "expire": ["layaway.manage"],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        status_param = self.request.query_params.get("status")
        customer_phone = self.request.query_params.get("customer_phone")
        customer_name = self.request.query_params.get("customer_name")
        query = self.request.query_params.get("q")
        expires_before = self.request.query_params.get("expires_before")
        expires_after = self.request.query_params.get("expires_after")
        due_today = self.request.query_params.get("due_today")
        expired = self.request.query_params.get("expired")
        exclude_settled = self.request.query_params.get("exclude_settled")

        if status_param:
            queryset = queryset.filter(status=status_param)
        if customer_phone:
            normalized = normalize_phone(customer_phone)
            queryset = queryset.filter(Q(customer__phone_normalized=normalized) | Q(customer_phone__icontains=customer_phone))
        if customer_name:
            queryset = queryset.filter(Q(customer__name__icontains=customer_name) | Q(customer_name__icontains=customer_name))
        if query:
            normalized = normalize_phone(query)
            queryset = queryset.filter(
                Q(customer__name__icontains=query)
                | Q(customer_name__icontains=query)
                | Q(customer__phone__icontains=query)
                | Q(customer__phone_normalized__icontains=normalized)
                | Q(customer_phone__icontains=query)
            )
        if expires_before:
            queryset = queryset.filter(expires_at__lte=expires_before)
        if expires_after:
            queryset = queryset.filter(expires_at__gte=expires_after)
        if str(due_today).lower() in {"1", "true", "yes"}:
            today = timezone.localdate()
            queryset = queryset.filter(expires_at__date=today)
        if str(expired).lower() in {"1", "true", "yes"}:
            queryset = queryset.filter(status=LayawayStatus.ACTIVE, expires_at__lt=timezone.now())
        if str(exclude_settled).lower() in {"1", "true", "yes"}:
            queryset = queryset.exclude(status=LayawayStatus.SETTLED)
        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return LayawayCreateSerializer
        return LayawaySerializer

    @staticmethod
    def _resolve_role(user):
        group_names = set(user.groups.values_list("name", flat=True))
        for role in (UserRole.ADMIN, UserRole.CASHIER, UserRole.INVESTOR):
            if role in group_names:
                return role
        return getattr(user, "role", UserRole.CASHIER)

    @staticmethod
    def _get_or_create_credit(customer):
        credit = CustomerCredit.objects.filter(customer=customer).first()
        if credit:
            return credit
        return CustomerCredit.objects.create(customer=customer, customer_name=customer.name, customer_phone=customer.phone)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            customer_data = serializer.validated_data["customer"]
            customer = Customer.get_or_create_by_phone(
                phone=customer_data["phone"],
                name=customer_data["name"],
                notes=customer_data.get("notes", ""),
            )
            lines = serializer.validated_data["lines"]
            deposit_payments = serializer.validated_data["deposit_payments"]
            total = serializer.validated_data["_total"]
            subtotal = serializer.validated_data["_subtotal"]
            total_qty = serializer.validated_data["_total_qty"]
            deposit_total = serializer.validated_data["_deposit_total"]
            first_line = lines[0]

            layaway = Layaway.objects.create(
                customer=customer,
                product=first_line["product"],
                qty=total_qty,
                customer_name=customer.name,
                customer_phone=customer.phone,
                subtotal=subtotal,
                total=total,
                amount_paid=deposit_total,
                total_price=total,
                deposit_amount=deposit_total,
                expires_at=serializer.validated_data["expires_at"],
                notes=serializer.validated_data.get("notes", ""),
                created_by=request.user,
            )

            for line in lines:
                line_obj = LayawayLine.objects.create(layaway=layaway, **line)
                InventoryMovement.objects.create(
                    product=line_obj.product,
                    movement_type=MovementType.RESERVED,
                    quantity_delta=-line_obj.qty,
                    reference_type="layaway_reserve",
                    reference_id=str(layaway.id),
                    note="Layaway reserve",
                    created_by=request.user,
                )

            for payment in deposit_payments:
                LayawayPayment.objects.create(
                    layaway=layaway,
                    created_by=request.user,
                    reference_type="layaway_create",
                    reference_id=str(layaway.id),
                    **payment,
                )

            record_audit(
                actor=request.user,
                action="layaway.create",
                entity_type="layaway",
                entity_id=layaway.id,
                payload={"deposit": str(deposit_total), "customer_id": str(customer.id)},
            )

        response_serializer = LayawaySerializer(layaway, context=self.get_serializer_context())
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def payments(self, request, pk=None):
        serializer = LayawayPaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                layaway = (
                    Layaway.objects.select_for_update()
                    .prefetch_related("payments", "lines")
                    .get(pk=pk)
                )
                if layaway.status != LayawayStatus.ACTIVE:
                    return Response({"code": "invalid_state", "detail": "El apartado no esta activo.", "fields": {}}, status=400)
                updated_layaway = self._apply_payments(layaway, serializer.validated_data["payments"], request.user)
        except ValueError as exc:
            return Response({"code": "invalid_payment", "detail": str(exc), "fields": {}}, status=400)

        return Response(LayawaySerializer(updated_layaway, context=self.get_serializer_context()).data, status=200)

    @action(detail=True, methods=["post"])
    def settle(self, request, pk=None):
        serializer = LayawayPaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                layaway = (
                    Layaway.objects.select_for_update()
                    .prefetch_related("payments", "lines")
                    .get(pk=pk)
                )
                if layaway.status != LayawayStatus.ACTIVE:
                    return Response({"code": "invalid_state", "detail": "El apartado no esta activo.", "fields": {}}, status=400)
                updated_layaway = self._apply_payments(layaway, serializer.validated_data["payments"], request.user)
                if updated_layaway.status != LayawayStatus.SETTLED:
                    due = (updated_layaway.total - updated_layaway.amount_paid).quantize(Decimal("0.01"))
                    raise ValueError(f"El apartado aun tiene saldo pendiente: {due}.")
        except ValueError as exc:
            return Response({"code": "invalid_payment", "detail": str(exc), "fields": {}}, status=400)

        return Response(LayawaySerializer(updated_layaway, context=self.get_serializer_context()).data, status=200)

    @action(detail=True, methods=["post"])
    def extend(self, request, pk=None):
        layaway = self.get_object()
        if layaway.status != LayawayStatus.ACTIVE:
            return Response({"code": "invalid_state", "detail": "Solo puedes extender apartados activos.", "fields": {}}, status=400)

        serializer = LayawayExtendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_expires_at = serializer.validated_data["new_expires_at"]
        if new_expires_at <= timezone.now():
            return Response({"code": "invalid_state", "detail": "La nueva fecha debe estar en el futuro.", "fields": {}}, status=400)
        if new_expires_at <= layaway.expires_at:
            return Response(
                {"code": "invalid_state", "detail": "La nueva fecha debe ser mayor a la fecha actual.", "fields": {}},
                status=400,
            )

        with transaction.atomic():
            old_expires_at = layaway.expires_at
            layaway.expires_at = new_expires_at
            layaway.save(update_fields=["expires_at", "updated_at"])
            LayawayExtensionLog.objects.create(
                layaway=layaway,
                old_expires_at=old_expires_at,
                new_expires_at=new_expires_at,
                reason=serializer.validated_data.get("reason", ""),
                created_by=request.user,
            )
            record_audit(
                actor=request.user,
                action="layaway.extend",
                entity_type="layaway",
                entity_id=layaway.id,
                payload={"old_expires_at": old_expires_at.isoformat(), "new_expires_at": new_expires_at.isoformat()},
            )

        return Response(LayawaySerializer(layaway, context=self.get_serializer_context()).data, status=200)

    @action(detail=True, methods=["post"])
    def expire(self, request, pk=None):
        user_role = self._resolve_role(request.user)
        force = str(request.data.get("force", "false")).lower() in {"1", "true", "yes"}

        with transaction.atomic():
            layaway = (
                Layaway.objects.select_for_update()
                .prefetch_related("lines")
                .get(pk=pk)
            )
            if layaway.status != LayawayStatus.ACTIVE:
                return Response({"code": "invalid_state", "detail": "El apartado no esta activo.", "fields": {}}, status=400)
            if timezone.now() < layaway.expires_at and not (force and user_role == UserRole.ADMIN):
                return Response(
                    {"code": "invalid_state", "detail": "El apartado aun no vence. Solo admin puede forzar vencimiento.", "fields": {}},
                    status=400,
                )
            layaway.status = LayawayStatus.EXPIRED
            layaway.save(update_fields=["status", "updated_at"])

            for line in layaway.lines.all():
                InventoryMovement.objects.create(
                    product=line.product,
                    movement_type=MovementType.RELEASED,
                    quantity_delta=line.qty,
                    reference_type="layaway_expire",
                    reference_id=str(layaway.id),
                    note="Layaway expired release",
                    created_by=request.user,
                )

            if layaway.customer_id and layaway.amount_paid > 0:
                credit = self._get_or_create_credit(layaway.customer)
                credit.balance = (credit.balance + layaway.amount_paid).quantize(Decimal("0.01"))
                credit.save(update_fields=["balance", "updated_at", "customer_name", "customer_phone"])

            record_audit(
                actor=request.user,
                action="layaway.expire",
                entity_type="layaway",
                entity_id=layaway.id,
                payload={"credit_added": str(layaway.amount_paid)},
            )

        return Response(LayawaySerializer(layaway, context=self.get_serializer_context()).data, status=200)

    def _apply_payments(self, layaway, payments, user):
        payment_sum = sum((payment["amount"] for payment in payments), Decimal("0.00")).quantize(Decimal("0.01"))
        due = (layaway.total - layaway.amount_paid).quantize(Decimal("0.01"))
        if payment_sum > due:
            raise ValueError("La suma de pagos excede el saldo pendiente.")

        if layaway.customer_id:
            credit_requested = sum(
                (payment["amount"] for payment in payments if payment["method"] == PaymentMethod.CUSTOMER_CREDIT),
                Decimal("0.00"),
            ).quantize(Decimal("0.01"))
            if credit_requested > 0:
                credit = self._get_or_create_credit(layaway.customer)
                credit = CustomerCredit.objects.select_for_update().get(pk=credit.pk)
                if credit_requested > credit.balance:
                    raise ValueError("El saldo a favor solicitado excede el disponible.")
                credit.balance = (credit.balance - credit_requested).quantize(Decimal("0.01"))
                credit.save(update_fields=["balance", "updated_at", "customer_name", "customer_phone"])

        for payment in payments:
            LayawayPayment.objects.create(
                layaway=layaway,
                created_by=user,
                reference_type="layaway_payment",
                reference_id=str(layaway.id),
                **payment,
            )

        layaway.amount_paid = (layaway.amount_paid + payment_sum).quantize(Decimal("0.01"))
        layaway.deposit_amount = layaway.payments.order_by("created_at").first().amount
        if layaway.amount_paid == layaway.total:
            sale = self._create_settled_sale(layaway, user)
            layaway.status = LayawayStatus.SETTLED
            layaway.settled_sale_id = sale.id
            layaway.save(update_fields=["amount_paid", "deposit_amount", "status", "settled_sale_id", "updated_at"])
        else:
            layaway.save(update_fields=["amount_paid", "deposit_amount", "updated_at"])

        record_audit(
            actor=user,
            action="layaway.payment",
            entity_type="layaway",
            entity_id=layaway.id,
            payload={"amount": str(payment_sum), "new_amount_paid": str(layaway.amount_paid)},
        )
        return layaway

    @staticmethod
    def _create_settled_sale(layaway, user):
        sale = Sale.objects.create(
            cashier=user,
            customer=layaway.customer,
            status=SaleStatus.CONFIRMED,
            subtotal=layaway.subtotal,
            discount_amount=(layaway.subtotal - layaway.total).quantize(Decimal("0.01")),
            total=layaway.total,
            confirmed_at=timezone.now(),
        )
        for line in layaway.lines.all():
            SaleLine.objects.create(
                sale=sale,
                product=line.product,
                qty=line.qty,
                unit_price=line.unit_price,
                unit_cost=line.unit_cost,
                discount_pct=line.discount_pct,
            )
        for payment in LayawayPayment.objects.filter(layaway=layaway).order_by("created_at"):
            Payment.objects.create(
                sale=sale,
                method=payment.method,
                amount=payment.amount,
                card_type=payment.card_type or None,
                commission_rate=payment.commission_rate,
                card_plan_code=payment.card_plan_code,
                card_plan_label=payment.card_plan_label,
                installments_months=payment.installments_months,
            )
        for line in sale.lines.all():
            LayawayViewSet._apply_investor_ledger_for_line(sale, line)

        record_audit(
            actor=user,
            action="sale.confirm",
            entity_type="sale",
            entity_id=sale.id,
            payload={"total": str(sale.total), "source": "layaway"},
        )
        return sale

    @staticmethod
    def _sale_commission_total(sale):
        commission_total = Decimal("0")
        for payment in sale.payments.all():
            if payment.method != PaymentMethod.CARD:
                continue
            commission_rate = payment.commission_rate or Decimal("0")
            commission_total += payment.amount * commission_rate
        return commission_total

    @staticmethod
    def _apply_investor_ledger_for_line(sale, line):
        remaining_qty = line.qty
        assignments = InvestorAssignment.objects.filter(product=line.product, qty_assigned__gt=0).order_by("created_at")

        gross_line_revenue = line.qty * line.unit_price
        line_discount = gross_line_revenue * line.discount_pct / Decimal("100")
        net_revenue = gross_line_revenue - line_discount
        commission_total = LayawayViewSet._sale_commission_total(sale)

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


class CustomerCreditViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CustomerCredit.objects.select_related("customer").order_by("-updated_at")
    serializer_class = CustomerCreditSerializer
    permission_classes = [RolePermission]
    capability_map = {"list": ["layaway.manage"], "retrieve": ["layaway.manage"], "apply": ["layaway.manage"]}

    def get_queryset(self):
        queryset = super().get_queryset()
        customer_id = self.request.query_params.get("customer")
        customer_phone = self.request.query_params.get("customer_phone")
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        if customer_phone:
            normalized = normalize_phone(customer_phone)
            queryset = queryset.filter(Q(customer__phone_normalized=normalized) | Q(customer_phone__icontains=customer_phone))
        return queryset

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        amount = Decimal(str(request.data.get("amount", "0"))).quantize(Decimal("0.01"))
        reference_type = str(request.data.get("reference_type", "manual")).strip() or "manual"
        reference_id = str(request.data.get("reference_id", "")).strip() or "-"

        with transaction.atomic():
            credit = CustomerCredit.objects.select_for_update().get(pk=pk)
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
            credit.balance = (credit.balance - amount).quantize(Decimal("0.01"))
            credit.save(update_fields=["balance", "updated_at", "customer_name", "customer_phone"])
            record_audit(
                actor=request.user,
                action="customer_credit.apply",
                entity_type="customer_credit",
                entity_id=credit.id,
                payload={"amount": str(amount), "reference_type": reference_type, "reference_id": reference_id},
            )
        return Response(self.get_serializer(credit).data, status=200)
