from django.urls import path

from common.branding_views import BrandLogoView, BrandSettingsView
from common.dashboard_views import DashboardView
from common.reminders_views import ReminderCountView, ReminderListView
from common.search_views import GlobalSearchView
from common.timeline_views import CustomerTimelineView


urlpatterns = [
    path("branding/", BrandSettingsView.as_view(), name="branding-settings-api"),
    path("branding/logo/", BrandLogoView.as_view(), name="branding-logo"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("reminders/", ReminderListView.as_view(), name="reminders"),
    path("reminders/count/", ReminderCountView.as_view(), name="reminders-count"),
    path("search/", GlobalSearchView.as_view(), name="global-search"),
    path(
        "customers/<int:customer_id>/timeline/",
        CustomerTimelineView.as_view(),
        name="customer-timeline",
    ),
]
