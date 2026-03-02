from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce, Greatest
from rest_framework import generics
from rest_framework import serializers
from rest_framework.response import Response

from apps.catalog.models import Product
from apps.catalog.querysets import with_inventory_metrics
from apps.common.permissions import RolePermission
from apps.expenses.models import Expense, ExpenseStatus
from apps.investors.models import InvestorAssignment
from apps.ledger.models import LedgerEntry, LedgerEntryType
from apps.purchases.models import PurchaseReceipt, ReceiptStatus
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
    def _line_net_amount():
        return ExpressionWrapper(
            F("qty") * F("unit_price") * (Value(Decimal("1.00")) - (F("discount_pct") / Value(Decimal("100.00")))),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )

    @staticmethod
    def _line_cost_amount():
        return ExpressionWrapper(
            F("qty") * F("unit_cost"),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )

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
        return list(
            SaleLine.objects.filter(sale__in=confirmed_sales)
            .values("product_id", "product__sku", "product__name")
            .annotate(
                units_sold=Coalesce(Sum("qty"), 0, output_field=DecimalField(max_digits=12, decimal_places=2)),
                sales_amount=Coalesce(
                    Sum(SalesMetricsMixin._line_net_amount()),
                    0,
                    output_field=DecimalField(max_digits=16, decimal_places=2),
                ),
            )
            .order_by("-units_sold", "-sales_amount")[:top_limit]
        )

    @staticmethod
    def _gross_profit_for(confirmed_sales):
        profit_expr = ExpressionWrapper(
            SalesMetricsMixin._line_net_amount() - SalesMetricsMixin._line_cost_amount(),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
        return SaleLine.objects.filter(sale__in=confirmed_sales).aggregate(
            gross_profit=Coalesce(
                Sum(profit_expr),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            )
        )["gross_profit"]

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
        queryset = Expense.objects.filter(status=ExpenseStatus.PAID)
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

    @staticmethod
    def _purchase_receipts_queryset(date_from, date_to):
        queryset = PurchaseReceipt.objects.filter(status=ReceiptStatus.POSTED)
        if date_from:
            queryset = queryset.filter(posted_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(posted_at__date__lte=date_to)
        return queryset

    @staticmethod
    def _purchase_summary(receipts):
        return receipts.aggregate(
            purchase_spend=Coalesce(
                Sum("total"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
            purchase_count=Count("id"),
        )

    @staticmethod
    def _assignments_queryset(date_from=None, date_to=None):
        queryset = InvestorAssignment.objects.select_related("product")
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset

    @staticmethod
    def _investor_profit_share_total(confirmed_sales):
        sale_ids = [str(sale_id) for sale_id in confirmed_sales.values_list("id", flat=True)]
        if not sale_ids:
            return Decimal("0.00")
        return (
            LedgerEntry.objects.filter(
                entry_type=LedgerEntryType.PROFIT_SHARE,
                reference_type="sale",
                reference_id__in=sale_ids,
            ).aggregate(
                total=Coalesce(
                    Sum("profit_delta"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=16, decimal_places=2),
                )
            )["total"]
        )

    @classmethod
    def _investor_sales_split(cls, *, date_to, confirmed_sales):
        replay_sales = Sale.objects.filter(status=SaleStatus.CONFIRMED)
        if date_to:
            replay_sales = replay_sales.filter(confirmed_at__date__lte=date_to)
        replay_sales = replay_sales.prefetch_related("lines").order_by("confirmed_at", "created_at")

        range_sale_ids = {str(sale_id) for sale_id in confirmed_sales.values_list("id", flat=True)}
        if not range_sale_ids:
            return {
                "investor_backed_sales_total": Decimal("0.00"),
                "store_owned_sales_total": Decimal("0.00"),
            }

        assignments_by_product = defaultdict(list)
        for assignment in cls._assignments_queryset(date_to=date_to).order_by("created_at", "id"):
            assignments_by_product[str(assignment.product_id)].append(assignment)

        consumed_by_assignment = defaultdict(lambda: Decimal("0.00"))
        investor_backed_sales_total = Decimal("0.00")
        store_owned_sales_total = Decimal("0.00")

        for sale in replay_sales:
            for line in sale.lines.all():
                line_amount = line.qty * line.unit_price
                line_discount = line_amount * line.discount_pct / Decimal("100.00")
                line_net_revenue = line_amount - line_discount
                remaining_qty = line.qty
                consumed_revenue = Decimal("0.00")

                for assignment in assignments_by_product.get(str(line.product_id), []):
                    if assignment.created_at > sale.confirmed_at:
                        continue

                    available = assignment.qty_assigned - consumed_by_assignment[str(assignment.id)]
                    if available <= 0 or remaining_qty <= 0:
                        continue

                    consumed = min(available, remaining_qty)
                    consumed_by_assignment[str(assignment.id)] += consumed
                    remaining_qty -= consumed
                    consumed_revenue += line_net_revenue * (consumed / line.qty)

                if str(sale.id) not in range_sale_ids:
                    continue

                investor_backed_sales_total += consumed_revenue
                store_owned_sales_total += line_net_revenue - consumed_revenue

        return {
            "investor_backed_sales_total": investor_backed_sales_total.quantize(Decimal("0.01")),
            "store_owned_sales_total": store_owned_sales_total.quantize(Decimal("0.01")),
        }

    @staticmethod
    def _inventory_snapshot():
        store_owned_units_expr = Greatest(F("stock") - F("investor_reserved_qty"), Value(Decimal("0.00")))
        store_owned_cost_expr = ExpressionWrapper(
            store_owned_units_expr * Coalesce(F("cost_price"), Value(Decimal("0.00"))),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
        stock_value_retail = ExpressionWrapper(
            F("stock") * F("default_price"),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
        store_owned_potential_expr = ExpressionWrapper(
            store_owned_units_expr * (F("default_price") - Coalesce(F("cost_price"), Value(Decimal("0.00")))),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
        inventory = with_inventory_metrics(Product.objects.filter(is_active=True))
        product_snapshot = inventory.aggregate(
            store_owned_cost_value=Coalesce(
                Sum(store_owned_cost_expr),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
            retail_value=Coalesce(
                Sum(stock_value_retail),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
            store_owned_potential_profit=Coalesce(
                Sum(store_owned_potential_expr),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
            total_units=Coalesce(
                Sum("stock"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            store_owned_units=Coalesce(
                Sum(store_owned_units_expr),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        )

        open_assignments = InvestorAssignment.objects.select_related("product").filter(qty_assigned__gt=F("qty_sold"))
        assignment_cost_expr = ExpressionWrapper(
            (F("qty_assigned") - F("qty_sold")) * F("unit_cost"),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
        assignment_profit_expr = ExpressionWrapper(
            (F("qty_assigned") - F("qty_sold")) * (F("product__default_price") - F("unit_cost")),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
        assignment_snapshot = open_assignments.aggregate(
            investor_assigned_units=Coalesce(
                Sum(F("qty_assigned") - F("qty_sold")),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            investor_assigned_cost_value=Coalesce(
                Sum(assignment_cost_expr),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
            investor_assigned_potential_profit=Coalesce(
                Sum(assignment_profit_expr),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
        )

        total_cost_value = (
            Decimal(str(product_snapshot["store_owned_cost_value"]))
            + Decimal(str(assignment_snapshot["investor_assigned_cost_value"]))
        ).quantize(Decimal("0.01"))
        total_potential_profit = (
            Decimal(str(product_snapshot["store_owned_potential_profit"]))
            + Decimal(str(assignment_snapshot["investor_assigned_potential_profit"]))
        ).quantize(Decimal("0.01"))

        snapshot = {
            "cost_value": total_cost_value,
            "retail_value": product_snapshot["retail_value"],
            "potential_profit": total_potential_profit,
            "total_units": product_snapshot["total_units"],
            "store_owned_units": product_snapshot["store_owned_units"],
            "investor_assigned_units": assignment_snapshot["investor_assigned_units"],
            "store_owned_cost_value": product_snapshot["store_owned_cost_value"],
            "investor_assigned_cost_value": assignment_snapshot["investor_assigned_cost_value"],
            "store_owned_potential_profit": product_snapshot["store_owned_potential_profit"],
            "investor_assigned_potential_profit": assignment_snapshot["investor_assigned_potential_profit"],
        }
        snapshot["gross_margin_pct"] = (
            (Decimal(str(snapshot["potential_profit"])) / Decimal(str(snapshot["retail_value"])) * Decimal("100.00")).quantize(
                Decimal("0.01")
            )
            if Decimal(str(snapshot["retail_value"])) > 0
            else Decimal("0.00")
        )
        return snapshot

    def _build_metrics_payload(self, params):
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        confirmed_sales = self._apply_date_range(
            Sale.objects.filter(status=SaleStatus.CONFIRMED),
            date_from,
            date_to,
        )
        purchases = self._purchase_receipts_queryset(date_from, date_to)
        purchase_summary = self._purchase_summary(purchases)
        gross_profit_total = self._gross_profit_for(confirmed_sales)
        investor_profit_share_total = self._investor_profit_share_total(confirmed_sales)
        sales_split = self._investor_sales_split(date_to=date_to, confirmed_sales=confirmed_sales)
        investor_assignment_summary = self._assignments_queryset(date_from=date_from, date_to=date_to).aggregate(
            inventory_cost_assigned_to_investors=Coalesce(
                Sum(
                    ExpressionWrapper(
                        F("qty_assigned") * F("unit_cost"),
                        output_field=DecimalField(max_digits=16, decimal_places=2),
                    )
                ),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            ),
        )
        store_profit_share_total = (
            Decimal(str(gross_profit_total)) - Decimal(str(investor_profit_share_total))
        ).quantize(Decimal("0.01"))
        store_net_inventory_exposure_change = (
            Decimal(str(purchase_summary["purchase_spend"]))
            - Decimal(str(investor_assignment_summary["inventory_cost_assigned_to_investors"]))
        ).quantize(Decimal("0.01"))

        return {
            **self._summary_for(confirmed_sales),
            "gross_profit": gross_profit_total,
            "gross_profit_total": gross_profit_total,
            **purchase_summary,
            "inventory_snapshot": self._inventory_snapshot(),
            "investor_metrics": {
                **sales_split,
                "investor_profit_share_total": investor_profit_share_total,
                "store_profit_share_total": store_profit_share_total,
                "inventory_cost_assigned_to_investors": investor_assignment_summary["inventory_cost_assigned_to_investors"],
                "store_net_inventory_exposure_change": store_net_inventory_exposure_change,
            },
            "range": {"date_from": date_from, "date_to": date_to},
            "top_products": self._top_products_for(confirmed_sales, params["top_limit"]),
            "payment_breakdown": self._payment_breakdown_for(confirmed_sales),
        }, confirmed_sales, store_profit_share_total


class SalesMetricsView(SalesMetricsMixin, generics.GenericAPIView):
    def get(self, request, *args, **kwargs):
        query_serializer = SalesMetricsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        metrics_payload, _, _ = self._build_metrics_payload(query_serializer.validated_data)
        return Response(metrics_payload)


class SalesReportView(SalesMetricsMixin, generics.GenericAPIView):
    def get(self, request, *args, **kwargs):
        query_serializer = SalesMetricsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        metrics_payload, confirmed_sales, store_profit_share_total = self._build_metrics_payload(query_serializer.validated_data)
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
            "net_profit": (
                Decimal(str(store_profit_share_total)) - Decimal(str(expense_summary["total_expenses"]))
            ).quantize(Decimal("0.01")),
        }
        return Response(report_payload)
