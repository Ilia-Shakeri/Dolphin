from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from common.permissions import IsActiveAuthenticated
from common.views import HealthView, LivenessView, ReadinessView


def build_urlpatterns():
    patterns = [
        path("api/v1/auth/", include("accounts.auth_urls")),
        path("api/v1/", include("accounts.urls")),
        path("api/v1/", include("auditlog.urls")),
        path("api/v1/", include("reports.urls")),
        path("api/v1/", include("sales.urls")),
        path("api/v1/", include("aftersales.urls")),
        path("api/v1/", include("communications.urls")),
        path("api/v1/", include("inventory.urls")),
        path("api/v1/", include("billing.urls")),
        path("api/v1/health/", HealthView.as_view(), name="health"),
        path("api/v1/health/live/", LivenessView.as_view(), name="health-live"),
        path("api/v1/health/ready/", ReadinessView.as_view(), name="health-ready"),
    ]
    # Django Admin is a server-administration plane reserved for the product
    # owner's management path. It is registered only when explicitly enabled, so
    # the default customer deployment serves no /admin/ route at all and the
    # reverse proxy denies it as a second, independent layer.
    if getattr(settings, "ENABLE_DJANGO_ADMIN", False):
        patterns.insert(0, path("admin/", admin.site.urls))
    if getattr(settings, "ENABLE_API_DOCS", False):
        from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

        patterns.extend([
            path(
                "api/v1/schema/",
                SpectacularAPIView.as_view(permission_classes=[IsActiveAuthenticated]),
                name="schema",
            ),
            path(
                "api/v1/docs/",
                SpectacularSwaggerView.as_view(
                    url_name="schema",
                    permission_classes=[IsActiveAuthenticated],
                ),
                name="docs",
            ),
        ])
    patterns.append(path("", include("common.ui_urls")))
    return patterns


urlpatterns = build_urlpatterns()

handler400 = "common.error_views.bad_request"
handler403 = "common.error_views.permission_denied"
handler404 = "common.error_views.page_not_found"
handler500 = "common.error_views.server_error"
