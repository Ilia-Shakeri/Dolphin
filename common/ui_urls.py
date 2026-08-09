from django.urls import path

from common.ui_views import KarizHomeView


app_name = "common_ui"

urlpatterns = [
    path("", KarizHomeView.as_view(), name="home"),
]
