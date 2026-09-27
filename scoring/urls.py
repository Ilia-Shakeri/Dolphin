from django.urls import path

from scoring.views import ScoringSettingsView

urlpatterns = [
    path("scoring-settings/", ScoringSettingsView.as_view(), name="scoring-settings"),
]
