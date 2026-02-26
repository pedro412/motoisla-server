from rest_framework.routers import DefaultRouter

from apps.expenses.views import ExpenseViewSet

router = DefaultRouter()
router.register("expenses", ExpenseViewSet, basename="expense")

urlpatterns = router.urls
