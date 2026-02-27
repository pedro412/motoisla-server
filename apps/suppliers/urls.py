from rest_framework.routers import DefaultRouter

from apps.suppliers.views import SupplierInvoiceParserViewSet, SupplierViewSet

router = DefaultRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("supplier-parsers", SupplierInvoiceParserViewSet, basename="supplier-parser")

urlpatterns = router.urls
