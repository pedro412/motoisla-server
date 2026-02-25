from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.sales.views import SaleViewSet
from apps.sales.views_metrics import SalesMetricsView

router = DefaultRouter()
router.register("sales", SaleViewSet, basename="sale")

urlpatterns = [
    path("metrics/", SalesMetricsView.as_view(), name="sales-metrics"),
]
urlpatterns += router.urls
