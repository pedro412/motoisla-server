from rest_framework.routers import DefaultRouter

from apps.imports.views import InvoiceImportBatchViewSet, InvoiceImportLineViewSet

router = DefaultRouter()
router.register("import-batches", InvoiceImportBatchViewSet, basename="import-batch")
router.register("import-lines", InvoiceImportLineViewSet, basename="import-line")

urlpatterns = router.urls
