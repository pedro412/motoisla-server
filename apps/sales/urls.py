from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.sales.views import (
    CardCommissionPlanListView,
    OperatingCostRateView,
    SaleProfitabilityPreviewView,
    SaleViewSet,
)
from apps.sales.views_metrics import SalesMetricsView, SalesReportView

router = DefaultRouter()
router.register("sales", SaleViewSet, basename="sale")

urlpatterns = [
    path("card-commission-plans/", CardCommissionPlanListView.as_view(), name="card-commission-plan-list"),
    path("sales/preview-profitability/", SaleProfitabilityPreviewView.as_view(), name="sales-preview-profitability"),
    path("profitability/operating-cost-rate/", OperatingCostRateView.as_view(), name="operating-cost-rate"),
    path("metrics/", SalesMetricsView.as_view(), name="sales-metrics"),
    path("reports/sales/", SalesReportView.as_view(), name="sales-report"),
]
urlpatterns += router.urls
