from django.db.models import DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import viewsets

from apps.catalog.models import Product, ProductImage
from apps.catalog.serializers import ProductImageSerializer, ProductSerializer
from apps.common.permissions import RolePermission
from apps.inventory.models import InventoryMovement


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["catalog.view"],
        "retrieve": ["catalog.view"],
        "create": ["catalog.manage"],
        "partial_update": ["catalog.manage"],
        "update": ["catalog.manage"],
        "destroy": ["catalog.manage"],
    }

    def get_queryset(self):
        stock_subquery = (
            InventoryMovement.objects.filter(product_id=OuterRef("pk"))
            .values("product_id")
            .annotate(total=Coalesce(Sum("quantity_delta"), Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))))
            .values("total")
        )
        queryset = Product.objects.all().annotate(
            stock=Coalesce(
                Subquery(stock_subquery, output_field=DecimalField(max_digits=12, decimal_places=2)),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            )
        )
        query = self.request.query_params.get("q")
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(sku__icontains=query))
        return queryset


class ProductImageViewSet(viewsets.ModelViewSet):
    queryset = ProductImage.objects.select_related("product")
    serializer_class = ProductImageSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["catalog.view"],
        "retrieve": ["catalog.view"],
        "create": ["catalog.manage"],
        "partial_update": ["catalog.manage"],
        "update": ["catalog.manage"],
        "destroy": ["catalog.manage"],
    }
