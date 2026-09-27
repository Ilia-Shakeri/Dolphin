from django.urls import path

from telephony import views

urlpatterns = [
    path("calls/", views.CallListView.as_view(), name="call-list"),
    path("calls/<int:call_id>/recording/", views.CallRecordingView.as_view(), name="call-recording"),
    path("telephony/extensions/", views.ExtensionListView.as_view(), name="extension-list"),
    path("telephony/extensions/<int:extension_id>/", views.ExtensionDetailView.as_view(), name="extension-detail"),
    path("telephony/originate/", views.OriginateView.as_view(), name="telephony-originate"),
    path("telephony/originate/<int:request_id>/", views.OriginateStatusView.as_view(), name="telephony-originate-status"),
    path("telephony/notifications/", views.NotificationInboxView.as_view(), name="telephony-notifications"),
    path("telephony/notifications/<int:notification_id>/", views.NotificationDetailView.as_view(), name="telephony-notification"),
    path(
        "telephony/notifications/<int:notification_id>/dismiss/",
        views.NotificationDismissView.as_view(),
        name="telephony-notification-dismiss",
    ),
    path("telephony/stats/", views.CallStatsView.as_view(), name="telephony-stats"),
]
