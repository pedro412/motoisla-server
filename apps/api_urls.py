from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("", include("apps.catalog.urls")),
    path("", include("apps.imports.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("", include("apps.purchases.urls")),
    path("", include("apps.sales.urls")),
    path("", include("apps.expenses.urls")),
    path("", include("apps.layaway.urls")),
    path("investors/", include("apps.investors.urls")),
]
