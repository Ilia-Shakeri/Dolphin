from django.urls import path

from profiles.views import PersonTimelineView

urlpatterns = [
    path(
        "profiles/<slug:person_type>/<int:person_id>/timeline/",
        PersonTimelineView.as_view(),
        name="person-timeline",
    ),
]
