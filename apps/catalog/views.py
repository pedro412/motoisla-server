from django.conf import settings
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import generics, viewsets
from rest_framework.permissions import AllowAny

from apps.audit.services import record_audit
from apps.catalog.models import Brand, Product, ProductImage, ProductType
from apps.catalog.querysets import with_inventory_metrics
from apps.catalog.serializers import (
    BrandSerializer,
    ProductImageSerializer,
    ProductSerializer,
    ProductTypeSerializer,
    PublicCatalogProductSerializer,
)
from apps.catalog.throttles import PublicCatalogAnonThrottle
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
        queryset = with_inventory_metrics(Product.objects.all()).prefetch_related("images")
        query = self.request.query_params.get("q")
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(sku__icontains=query))

        brand_id = self.request.query_params.get("brand")
        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)

        product_type_id = self.request.query_params.get("product_type")
        if product_type_id:
            queryset = queryset.filter(product_type_id=product_type_id)

        has_stock = self.request.query_params.get("has_stock")
        if has_stock is not None:
            normalized_has_stock = has_stock.strip().lower()
            if normalized_has_stock in {"1", "true", "yes"}:
                queryset = queryset.filter(stock__gt=0)
            elif normalized_has_stock in {"0", "false", "no"}:
                queryset = queryset.filter(stock__lte=0)
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
                "cost_price": str(product.cost_price) if product.cost_price is not None else None,
                "is_active": product.is_active,
            },
        )

    def perform_update(self, serializer):
        old_product = self.get_object()
        old_snapshot = {
            "sku": old_product.sku,
            "name": old_product.name,
            "default_price": str(old_product.default_price),
            "cost_price": str(old_product.cost_price) if old_product.cost_price is not None else None,
            "stock": str(getattr(old_product, "stock", InventoryMovement.current_stock(old_product.id))),
            "is_active": old_product.is_active,
        }
        product = serializer.save()
        new_snapshot = {
            "sku": product.sku,
            "name": product.name,
            "default_price": str(product.default_price),
            "cost_price": str(product.cost_price) if product.cost_price is not None else None,
            "stock": str(InventoryMovement.current_stock(product.id)),
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
                "cost_price": str(instance.cost_price) if instance.cost_price is not None else None,
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


class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all().order_by("name")
    serializer_class = BrandSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["catalog.view"],
        "retrieve": ["catalog.view"],
        "create": ["imports.manage"],
        "update": ["catalog.manage"],
        "partial_update": ["catalog.manage"],
        "destroy": ["catalog.manage"],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get("q")
        if query:
            query = query.strip()
            queryset = queryset.filter(Q(name__icontains=query) | Q(normalized_name__icontains=query))
        return queryset


class ProductTypeViewSet(viewsets.ModelViewSet):
    queryset = ProductType.objects.all().order_by("name")
    serializer_class = ProductTypeSerializer
    permission_classes = [RolePermission]
    capability_map = {
        "list": ["catalog.view"],
        "retrieve": ["catalog.view"],
        "create": ["imports.manage"],
        "update": ["catalog.manage"],
        "partial_update": ["catalog.manage"],
        "destroy": ["catalog.manage"],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get("q")
        if query:
            query = query.strip()
            queryset = queryset.filter(Q(name__icontains=query) | Q(normalized_name__icontains=query))
        return queryset


@method_decorator(cache_page(settings.PUBLIC_CATALOG_CACHE_TTL_SECONDS), name="dispatch")
class PublicCatalogListView(generics.ListAPIView):
    serializer_class = PublicCatalogProductSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicCatalogAnonThrottle]

    def get_queryset(self):
        queryset = Product.objects.filter(is_active=True).prefetch_related("images").order_by("name")
        query = self.request.query_params.get("q")
        if query:
            query = query.strip()
            queryset = queryset.filter(Q(name__icontains=query) | Q(sku__icontains=query))
        return queryset


@method_decorator(cache_page(settings.PUBLIC_CATALOG_CACHE_TTL_SECONDS), name="dispatch")
class PublicCatalogDetailView(generics.RetrieveAPIView):
    serializer_class = PublicCatalogProductSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicCatalogAnonThrottle]
    lookup_field = "sku"

    def get_queryset(self):
        return Product.objects.filter(is_active=True).prefetch_related("images")
