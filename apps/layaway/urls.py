from rest_framework.routers import DefaultRouter

from apps.layaway.views import CustomerCreditViewSet, CustomerViewSet, LayawayViewSet

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("layaways", LayawayViewSet, basename="layaway")
router.register("customer-credits", CustomerCreditViewSet, basename="customer-credit")

urlpatterns = router.urls
