from rest_framework.routers import DefaultRouter

from apps.layaway.views import CustomerCreditViewSet, LayawayViewSet

router = DefaultRouter()
router.register("layaways", LayawayViewSet, basename="layaway")
router.register("customer-credits", CustomerCreditViewSet, basename="customer-credit")

urlpatterns = router.urls
