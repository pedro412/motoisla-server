from django.db.models import DecimalField, Sum
from django.db.models.functions import Coalesce
from rest_framework import generics, viewsets
from rest_framework.response import Response

from apps.audit.services import record_audit
from apps.common.permissions import RolePermission
from apps.inventory.models import InventoryMovement, MovementType
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

    def get_queryset(self):
        queryset = super().get_queryset()
        product_id = self.request.query_params.get("product")
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        return queryset

    def perform_create(self, serializer):
        movement = serializer.save()
        action = "inventory.adjustment.create" if movement.movement_type == MovementType.ADJUSTMENT else "inventory.movement.create"
        record_audit(
            actor=self.request.user,
            action=action,
            entity_type="inventory_movement",
            entity_id=movement.id,
            payload={
                "product_id": str(movement.product_id),
                "movement_type": movement.movement_type,
                "quantity_delta": str(movement.quantity_delta),
                "reference_type": movement.reference_type,
                "reference_id": movement.reference_id,
            },
        )


class InventoryStockView(generics.GenericAPIView):
    permission_classes = [RolePermission]
    capability_map = {"get": ["inventory.view"]}

    def get(self, request, *args, **kwargs):
        product_id = request.query_params.get("product")
        queryset = InventoryMovement.objects.all()
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        queryset = queryset.values("product_id").annotate(
            stock=Coalesce(Sum("quantity_delta"), 0, output_field=DecimalField(max_digits=12, decimal_places=2))
        )
        return Response(list(queryset))
