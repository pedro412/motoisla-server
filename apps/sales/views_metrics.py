from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import generics
from rest_framework import serializers
from rest_framework.response import Response

from apps.common.permissions import RolePermission
from apps.expenses.models import Expense
from apps.sales.models import Payment, PaymentMethod, Sale, SaleLine, SaleStatus


class SalesMetricsQuerySerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    top_limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=10)

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError({"date_from": "date_from must be before or equal to date_to."})
        return attrs


class SalesMetricsMixin:
    permission_classes = [RolePermission]
    capability_map = {"get": ["metrics.view"]}

    @staticmethod
    def _apply_date_range(queryset, date_from, date_to):
        if date_from:
            queryset = queryset.filter(confirmed_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(confirmed_at__date__lte=date_to)
        return queryset

    @staticmethod
    def _summary_for(confirmed_sales):
        return confirmed_sales.aggregate(
            total_sales=Coalesce(
                Sum("total"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
            avg_ticket=Coalesce(
                Avg("total"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
            sales_count=Count("id"),
        )

    @staticmethod
    def _top_products_for(confirmed_sales, top_limit):
        line_net_amount = ExpressionWrapper(
            F("qty") * F("unit_price") * (Value(Decimal("1.00")) - (F("discount_pct") / Value(Decimal("100.00")))),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
        return list(
            SaleLine.objects.filter(sale__in=confirmed_sales)
            .values("product_id", "product__sku", "product__name")
            .annotate(
                units_sold=Coalesce(Sum("qty"), 0, output_field=DecimalField(max_digits=12, decimal_places=2)),
                sales_amount=Coalesce(
                    Sum(line_net_amount),
                    0,
                    output_field=DecimalField(max_digits=16, decimal_places=2),
                ),
            )
            .order_by("-units_sold", "-sales_amount")[:top_limit]
        )

    @staticmethod
    def _payment_breakdown_for(confirmed_sales):
        by_method = list(
            Payment.objects.filter(sale__in=confirmed_sales)
            .values("method")
            .annotate(
                total_amount=Coalesce(Sum("amount"), 0, output_field=DecimalField(max_digits=16, decimal_places=2)),
                transactions=Count("id"),
            )
            .order_by("method")
        )
        card_types = list(
            Payment.objects.filter(sale__in=confirmed_sales, method=PaymentMethod.CARD)
            .values("card_type")
            .annotate(
                total_amount=Coalesce(Sum("amount"), 0, output_field=DecimalField(max_digits=16, decimal_places=2)),
                transactions=Count("id"),
            )
            .order_by("card_type")
        )
        return {
            "by_method": by_method,
            "card_types": card_types,
        }

    @staticmethod
    def _sales_by_day(confirmed_sales):
        return list(
            confirmed_sales.values("confirmed_at__date")
            .annotate(
                total_sales=Coalesce(Sum("total"), Value(Decimal("0.00")), output_field=DecimalField(max_digits=16, decimal_places=2)),
                sales_count=Count("id"),
            )
            .order_by("confirmed_at__date")
        )

    @staticmethod
    def _sales_by_cashier(confirmed_sales):
        return list(
            confirmed_sales.values("cashier_id", "cashier__username")
            .annotate(
                total_sales=Coalesce(Sum("total"), Value(Decimal("0.00")), output_field=DecimalField(max_digits=16, decimal_places=2)),
                sales_count=Count("id"),
                avg_ticket=Coalesce(Avg("total"), Value(Decimal("0.00")), output_field=DecimalField(max_digits=16, decimal_places=2)),
            )
            .order_by("-total_sales")
        )

    @staticmethod
    def _expenses_queryset(date_from, date_to):
        queryset = Expense.objects.all()
        if date_from:
            queryset = queryset.filter(expense_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(expense_date__lte=date_to)
        return queryset

    @staticmethod
    def _expenses_summary(expenses):
        return expenses.aggregate(
            total_expenses=Coalesce(
                Sum("amount"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
            expenses_count=Count("id"),
        )

    @staticmethod
    def _expenses_by_category(expenses):
        return list(
            expenses.values("category")
            .annotate(
                total_amount=Coalesce(
                    Sum("amount"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=16, decimal_places=2),
                ),
                items_count=Count("id"),
            )
            .order_by("-total_amount", "category")
        )

    def _build_metrics_payload(self, params):
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        confirmed_sales = self._apply_date_range(
            Sale.objects.filter(status=SaleStatus.CONFIRMED),
            date_from,
            date_to,
        )
        return {
            **self._summary_for(confirmed_sales),
            "range": {"date_from": date_from, "date_to": date_to},
            "top_products": self._top_products_for(confirmed_sales, params["top_limit"]),
            "payment_breakdown": self._payment_breakdown_for(confirmed_sales),
        }, confirmed_sales


class SalesMetricsView(SalesMetricsMixin, generics.GenericAPIView):
    def get(self, request, *args, **kwargs):
        query_serializer = SalesMetricsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        metrics_payload, _ = self._build_metrics_payload(query_serializer.validated_data)
        return Response(metrics_payload)


class SalesReportView(SalesMetricsMixin, generics.GenericAPIView):
    def get(self, request, *args, **kwargs):
        query_serializer = SalesMetricsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        metrics_payload, confirmed_sales = self._build_metrics_payload(query_serializer.validated_data)
        expenses = self._expenses_queryset(
            query_serializer.validated_data.get("date_from"),
            query_serializer.validated_data.get("date_to"),
        )
        expense_summary = self._expenses_summary(expenses)
        report_payload = {
            **metrics_payload,
            "sales_by_day": self._sales_by_day(confirmed_sales),
            "sales_by_cashier": self._sales_by_cashier(confirmed_sales),
            "expenses_summary": {
                **expense_summary,
                "by_category": self._expenses_by_category(expenses),
            },
            "net_sales_after_expenses": (
                Decimal(str(metrics_payload["total_sales"])) - Decimal(str(expense_summary["total_expenses"]))
            ).quantize(Decimal("0.01")),
        }
        return Response(report_payload)
