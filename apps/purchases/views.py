from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.permissions import RolePermission
from apps.inventory.models import InventoryMovement, MovementType
from apps.purchases.models import PurchaseReceipt, ReceiptStatus
from apps.purchases.serializers import PurchaseReceiptSerializer


class PurchaseReceiptViewSet(viewsets.ModelViewSet):
    queryset = PurchaseReceipt.objects.select_related("supplier", "created_by").prefetch_related("lines")
    serializer_class = PurchaseReceiptSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["purchases.view"],
        "retrieve": ["purchases.view"],
        "create": ["purchases.manage"],
        "confirm": ["purchases.manage"],
    }

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        receipt = self.get_object()
        if receipt.status == ReceiptStatus.POSTED:
            return Response({"code": "already_confirmed", "detail": "Receipt already posted", "fields": {}}, status=200)

        with transaction.atomic():
            for line in receipt.lines.all():
                InventoryMovement.objects.create(
                    product=line.product,
                    movement_type=MovementType.INBOUND,
                    quantity_delta=line.qty,
                    reference_type="purchase_receipt",
                    reference_id=str(receipt.id),
                    note="Receipt posting",
                    created_by=request.user,
                )
            receipt.status = ReceiptStatus.POSTED
            receipt.posted_at = timezone.now()
            receipt.save(update_fields=["status", "posted_at"])

        return Response(self.get_serializer(receipt).data, status=status.HTTP_200_OK)
