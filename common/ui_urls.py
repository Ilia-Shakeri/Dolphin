from django.urls import path

from common.ui_views import (
    KarizActivityLogDetailView,
    KarizActivityLogListView,
    KarizCustomerDetailView,
    KarizCustomerListView,
    KarizHomeView,
    KarizInteractionDetailView,
    KarizInteractionListView,
    KarizLeadDetailView,
    KarizLeadListView,
    KarizLoginView,
    KarizProductDetailView,
    KarizProductListView,
    KarizSaleDetailView,
    KarizSaleListView,
    KarizUserPerformanceView,
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
    path("products/", KarizProductListView.as_view(), name="products"),
    path("products/<int:product_id>/", KarizProductDetailView.as_view(), name="product-detail"),
    path("sales/", KarizSaleListView.as_view(), name="sales"),
    path("sales/<int:sale_id>/", KarizSaleDetailView.as_view(), name="sale-detail"),
    path("reports/user-performance/", KarizUserPerformanceView.as_view(), name="user-performance"),
    path("activity-logs/", KarizActivityLogListView.as_view(), name="activity-logs"),
    path("activity-logs/<int:activity_log_id>/", KarizActivityLogDetailView.as_view(), name="activity-log-detail"),
]
