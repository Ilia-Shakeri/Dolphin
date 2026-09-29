from django.urls import path

from profiles.views import PersonAnalysisView, PersonCardsView, PersonScoreView, PersonTimelineView

urlpatterns = [
    path(
        "profiles/<slug:person_type>/<int:person_id>/timeline/",
        PersonTimelineView.as_view(),
        name="person-timeline",
    ),
    path("profiles/<slug:person_type>/<int:person_id>/cards/", PersonCardsView.as_view(), name="person-cards"),
    path("profiles/<slug:person_type>/<int:person_id>/analysis/", PersonAnalysisView.as_view(), name="person-analysis"),
    path("profiles/<slug:person_type>/<int:person_id>/score/", PersonScoreView.as_view(), name="person-score"),
]
