from rest_framework.routers import DefaultRouter

from apps.purchases.views import PurchaseReceiptViewSet

router = DefaultRouter()
router.register("purchase-receipts", PurchaseReceiptViewSet, basename="purchase-receipt")

urlpatterns = router.urls
