from django.urls import path

from common.ui_views import (
    KarizCustomerDetailView,
    KarizCustomerListView,
    KarizHomeView,
    KarizInteractionDetailView,
    KarizInteractionListView,
    KarizLeadDetailView,
    KarizLeadListView,
    KarizLoginView,
    KarizUserDetailView,
    KarizUserListView,
)


app_name = "common_ui"

urlpatterns = [
    path("login/", KarizLoginView.as_view(), name="login"),
    path("", KarizHomeView.as_view(), name="home"),
    path("users/", KarizUserListView.as_view(), name="users"),
    path("users/<int:user_id>/", KarizUserDetailView.as_view(), name="user-detail"),
    path("customers/", KarizCustomerListView.as_view(), name="customers"),
    path("customers/<int:customer_id>/", KarizCustomerDetailView.as_view(), name="customer-detail"),
    path("leads/", KarizLeadListView.as_view(), name="leads"),
    path("leads/<int:lead_id>/", KarizLeadDetailView.as_view(), name="lead-detail"),
    path("interactions/", KarizInteractionListView.as_view(), name="interactions"),
    path("interactions/<int:interaction_id>/", KarizInteractionDetailView.as_view(), name="interaction-detail"),
]
