from django.urls import path

from telephony import views

urlpatterns = [
    path("calls/", views.CallListView.as_view(), name="call-list"),
    path("calls/<int:call_id>/recording/", views.CallRecordingView.as_view(), name="call-recording"),
    path("telephony/extensions/", views.ExtensionListView.as_view(), name="extension-list"),
    path("telephony/extensions/<int:extension_id>/", views.ExtensionDetailView.as_view(), name="extension-detail"),
]
