from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.investors.views import (
    InvestorAssignmentViewSet,
    InvestorViewSet,
    MyInvestorProfileView,
    MyLedgerView,
)

router = DefaultRouter()
router.register("assignments", InvestorAssignmentViewSet, basename="investor-assignment")
router.register("", InvestorViewSet, basename="investor")

urlpatterns = [
    path("me/", MyInvestorProfileView.as_view(), name="investor-me"),
    path("me/ledger/", MyLedgerView.as_view(), name="investor-me-ledger"),
    path("", include(router.urls)),
]
