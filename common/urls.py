from django.urls import path

from common.branding_views import BrandLogoView, BrandSettingsView
from common.reminders_views import ReminderCountView, ReminderListView


urlpatterns = [
    path("branding/", BrandSettingsView.as_view(), name="branding-settings-api"),
    path("branding/logo/", BrandLogoView.as_view(), name="branding-logo"),
    path("reminders/", ReminderListView.as_view(), name="reminders"),
    path("reminders/count/", ReminderCountView.as_view(), name="reminders-count"),
]
