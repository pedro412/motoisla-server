from django.db.models import DecimalField, ExpressionWrapper, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.inventory.models import InventoryMovement
from apps.investors.models import InvestorAssignment


MONEY_FIELD = DecimalField(max_digits=12, decimal_places=2)


def with_inventory_metrics(queryset):
    stock_subquery = (
        InventoryMovement.objects.filter(product_id=OuterRef("pk"))
        .values("product_id")
        .annotate(total=Coalesce(Sum("quantity_delta"), Value(0, output_field=MONEY_FIELD)))
        .values("total")
    )
    reserved_subquery = (
        InvestorAssignment.objects.filter(product_id=OuterRef("pk"))
        .values("product_id")
        .annotate(
            total=Coalesce(
                Sum(ExpressionWrapper(F("qty_assigned") - F("qty_sold"), output_field=MONEY_FIELD)),
                Value(0, output_field=MONEY_FIELD),
            )
        )
        .values("total")
    )
    return queryset.annotate(
        stock=Coalesce(Subquery(stock_subquery, output_field=MONEY_FIELD), Value(0, output_field=MONEY_FIELD)),
        investor_reserved_qty=Coalesce(Subquery(reserved_subquery, output_field=MONEY_FIELD), Value(0, output_field=MONEY_FIELD)),
    )
