from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.catalog.views import (
    BrandViewSet,
    ProductImageViewSet,
    ProductTypeViewSet,
    ProductViewSet,
    PublicCatalogDetailView,
    PublicCatalogListView,
)

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("product-images", ProductImageViewSet, basename="product-image")
router.register("brands", BrandViewSet, basename="brand")
router.register("product-types", ProductTypeViewSet, basename="product-type")

urlpatterns = [
    path("public/catalog/", PublicCatalogListView.as_view(), name="public-catalog-list"),
    path("public/catalog/<str:sku>/", PublicCatalogDetailView.as_view(), name="public-catalog-detail"),
]
urlpatterns += router.urls
