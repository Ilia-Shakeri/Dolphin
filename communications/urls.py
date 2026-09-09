from django.urls import path

from communications.views import (
    InboundSMSDrilldownView,
    InboundSMSMessageDetailView,
    InboundSMSReportView,
    OutboundSMSListView,
    SendOutboundSMSView,
    SmsCampaignCancelView,
    SmsCampaignListCreateView,
    SmsProviderSettingsView,
    SmsTemplateDeleteView,
    SmsTemplateListCreateView,
    TestSmsProviderConnectionView,
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
    path("outbound-sms/campaigns/", SmsCampaignListCreateView.as_view(), name="sms-campaign-list"),
    path(
        "outbound-sms/campaigns/<int:pk>/cancel/",
        SmsCampaignCancelView.as_view(),
        name="sms-campaign-cancel",
    ),
    path("outbound-sms/templates/", SmsTemplateListCreateView.as_view(), name="sms-template-list"),
    path(
        "outbound-sms/templates/<int:pk>/delete/",
        SmsTemplateDeleteView.as_view(),
        name="sms-template-delete",
    ),
    path("sms-provider-settings/", SmsProviderSettingsView.as_view(), name="sms-provider-settings"),
    path(
        "sms-provider-settings/test/",
        TestSmsProviderConnectionView.as_view(),
        name="sms-provider-settings-test",
    ),
]
