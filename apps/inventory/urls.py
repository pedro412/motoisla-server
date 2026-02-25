from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.inventory.views import InventoryMovementViewSet, InventoryStockView

router = DefaultRouter()
router.register("movements", InventoryMovementViewSet, basename="inventory-movement")

urlpatterns = [
    path("stocks/", InventoryStockView.as_view(), name="inventory-stock"),
]
urlpatterns += router.urls
