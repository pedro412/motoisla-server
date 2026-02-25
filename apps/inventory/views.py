from django.db.models import DecimalField, Sum
from django.db.models.functions import Coalesce
from rest_framework import generics, viewsets
from rest_framework.response import Response

from apps.common.permissions import RolePermission
from apps.inventory.models import InventoryMovement
from apps.inventory.serializers import InventoryMovementSerializer


class InventoryMovementViewSet(viewsets.ModelViewSet):
    queryset = InventoryMovement.objects.select_related("product", "created_by")
    serializer_class = InventoryMovementSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["inventory.view"],
        "retrieve": ["inventory.view"],
        "create": ["inventory.manage"],
        "partial_update": ["inventory.manage"],
        "update": ["inventory.manage"],
        "destroy": ["inventory.manage"],
    }


class InventoryStockView(generics.GenericAPIView):
    permission_classes = [RolePermission]
    capability_map = {"get": ["inventory.view"]}

    def get(self, request, *args, **kwargs):
        product_id = request.query_params.get("product")
        queryset = InventoryMovement.objects.values("product_id").annotate(
            stock=Coalesce(Sum("quantity_delta"), 0, output_field=DecimalField(max_digits=12, decimal_places=2))
        )
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        return Response(list(queryset))
