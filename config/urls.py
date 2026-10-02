from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from common.permissions import IsActiveAuthenticated
from common.realtime_views import EventStreamView, RealtimeHealthView
from common.views import HealthView, LivenessView, ReadinessView
from integration.views import HandoffAcceptView  # PRELIMINARY, UNCOMMITTED — see integration/apps.py


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
        path("api/v1/", include("profiles.urls")),
        path("api/v1/", include("timeline.urls")),
        path("api/v1/", include("tasks.urls")),
        path("api/v1/", include("scoring.urls")),
        path("api/v1/", include("integrations.urls")),
        path("api/v1/", include("telephony.urls")),
        path("api/v1/", include("billing.urls")),
        path("api/v1/", include("attachments.urls")),
        path("api/v1/", include("chat.urls")),
        path("api/v1/", include("common.urls")),
        # PRELIMINARY, UNCOMMITTED — see integration/apps.py
        path("api/v1/", include("integration.urls")),
        path("integration/handoff/", HandoffAcceptView.as_view(), name="handoff-accept"),
        path("api/v1/realtime/events/", EventStreamView.as_view(), name="realtime-events"),
        path("api/v1/realtime/health/", RealtimeHealthView.as_view(), name="realtime-health"),
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
