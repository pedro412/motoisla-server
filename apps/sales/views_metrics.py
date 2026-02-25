from django.db.models import Avg, Count, Sum
from django.db.models.functions import Coalesce
from rest_framework import generics
from rest_framework.response import Response

from apps.common.permissions import RolePermission
from apps.sales.models import Sale, SaleStatus


class SalesMetricsView(generics.GenericAPIView):
    permission_classes = [RolePermission]
    capability_map = {"get": ["metrics.view"]}

    def get(self, request, *args, **kwargs):
        confirmed_sales = Sale.objects.filter(status=SaleStatus.CONFIRMED)
        summary = confirmed_sales.aggregate(
            total_sales=Coalesce(Sum("total"), 0),
            avg_ticket=Coalesce(Avg("total"), 0),
            sales_count=Count("id"),
        )
        return Response(summary)
