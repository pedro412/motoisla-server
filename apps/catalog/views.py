from django.db.models import DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import viewsets

from apps.audit.services import record_audit
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

    def perform_create(self, serializer):
        product = serializer.save()
        record_audit(
            actor=self.request.user,
            action="catalog.product.create",
            entity_type="product",
            entity_id=product.id,
            payload={
                "sku": product.sku,
                "name": product.name,
                "default_price": str(product.default_price),
                "is_active": product.is_active,
            },
        )

    def perform_update(self, serializer):
        old_product = self.get_object()
        old_snapshot = {
            "sku": old_product.sku,
            "name": old_product.name,
            "default_price": str(old_product.default_price),
            "is_active": old_product.is_active,
        }
        product = serializer.save()
        new_snapshot = {
            "sku": product.sku,
            "name": product.name,
            "default_price": str(product.default_price),
            "is_active": product.is_active,
        }
        record_audit(
            actor=self.request.user,
            action="catalog.product.update",
            entity_type="product",
            entity_id=product.id,
            payload={"before": old_snapshot, "after": new_snapshot},
        )

    def perform_destroy(self, instance):
        record_audit(
            actor=self.request.user,
            action="catalog.product.delete",
            entity_type="product",
            entity_id=instance.id,
            payload={
                "sku": instance.sku,
                "name": instance.name,
                "default_price": str(instance.default_price),
                "is_active": instance.is_active,
            },
        )
        super().perform_destroy(instance)


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

    def perform_create(self, serializer):
        image = serializer.save()
        record_audit(
            actor=self.request.user,
            action="catalog.product_image.create",
            entity_type="product_image",
            entity_id=image.id,
            payload={
                "product_id": str(image.product_id),
                "is_primary": image.is_primary,
            },
        )

    def perform_update(self, serializer):
        old_image = self.get_object()
        old_snapshot = {"image_url": old_image.image_url, "is_primary": old_image.is_primary}
        image = serializer.save()
        record_audit(
            actor=self.request.user,
            action="catalog.product_image.update",
            entity_type="product_image",
            entity_id=image.id,
            payload={
                "before": old_snapshot,
                "after": {"image_url": image.image_url, "is_primary": image.is_primary},
            },
        )

    def perform_destroy(self, instance):
        record_audit(
            actor=self.request.user,
            action="catalog.product_image.delete",
            entity_type="product_image",
            entity_id=instance.id,
            payload={"product_id": str(instance.product_id), "is_primary": instance.is_primary},
        )
        super().perform_destroy(instance)
