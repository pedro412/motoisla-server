from rest_framework.routers import DefaultRouter

from apps.expenses.views import ExpenseViewSet, FixedExpenseTemplateViewSet

router = DefaultRouter()
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("fixed-expense-templates", FixedExpenseTemplateViewSet, basename="fixed-expense-template")

urlpatterns = router.urls
