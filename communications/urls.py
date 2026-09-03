from django.urls import path

from communications.views import (
    InboundSMSDrilldownView,
    InboundSMSMessageDetailView,
    InboundSMSReportView,
    OutboundSMSListView,
    SendOutboundSMSView,
)


urlpatterns = [
    path("reports/inbound-sms/", InboundSMSReportView.as_view(), name="inbound-sms-report"),
    path("reports/inbound-sms/drilldown/", InboundSMSDrilldownView.as_view(), name="inbound-sms-drilldown"),
    path(
        "reports/inbound-sms/messages/<int:message_id>/",
        InboundSMSMessageDetailView.as_view(),
        name="inbound-sms-message-detail",
    ),
    path("outbound-sms/", OutboundSMSListView.as_view(), name="outbound-sms-list"),
    path("outbound-sms/send/", SendOutboundSMSView.as_view(), name="outbound-sms-send"),
]
