from django.urls import path

from common.branding_views import BrandLogoView, BrandSettingsView


urlpatterns = [
    path("branding/", BrandSettingsView.as_view(), name="branding-settings-api"),
    path("branding/logo/", BrandLogoView.as_view(), name="branding-logo"),
]
