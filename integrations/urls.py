from django.urls import path

from integrations import views

urlpatterns = [
    path("integrations/providers/", views.ProvidersView.as_view(), name="integration-providers"),
    path("integrations/", views.IntegrationListView.as_view(), name="integration-list"),
    path("integrations/<int:integration_id>/", views.IntegrationDetailView.as_view(), name="integration-detail"),
    path("integrations/<int:integration_id>/test/", views.IntegrationTestView.as_view(), name="integration-test"),
    path("integrations/<int:integration_id>/webhook/", views.InboundWebhookView.as_view(), name="integration-webhook"),
    path("integration-logs/", views.IntegrationLogView.as_view(), name="integration-logs"),
    path("webhook-subscriptions/", views.SubscriptionListView.as_view(), name="webhook-subscription-list"),
    path("webhook-subscriptions/<int:subscription_id>/", views.SubscriptionDetailView.as_view(), name="webhook-subscription-detail"),
    path("webhook-subscriptions/<int:subscription_id>/ping/", views.SubscriptionPingView.as_view(), name="webhook-subscription-ping"),
    path("webhook-subscriptions/<int:subscription_id>/deliveries/", views.SubscriptionDeliveriesView.as_view(), name="webhook-subscription-deliveries"),
    path("api-tokens/", views.TokenListView.as_view(), name="api-token-list"),
    path("api-tokens/<int:token_id>/revoke/", views.TokenRevokeView.as_view(), name="api-token-revoke"),
]
