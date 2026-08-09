from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from common.permissions import IsActiveAuthenticated
from common.views import HealthView, LivenessView, ReadinessView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("accounts.auth_urls")),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("sales.urls")),
    path("api/v1/health/", HealthView.as_view(), name="health"),
    path("api/v1/health/live/", LivenessView.as_view(), name="health-live"),
    path("api/v1/health/ready/", ReadinessView.as_view(), name="health-ready"),
    path("api/v1/schema/", SpectacularAPIView.as_view(permission_classes=[IsActiveAuthenticated]), name="schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[IsActiveAuthenticated]), name="docs"),
]
