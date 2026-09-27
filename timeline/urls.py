from django.urls import path

from timeline.views import PersonNoteDetailView, PersonNotesView

urlpatterns = [
    path("profiles/<slug:person_type>/<int:person_id>/notes/", PersonNotesView.as_view(), name="person-notes"),
    path("person-notes/<int:note_id>/", PersonNoteDetailView.as_view(), name="person-note-detail"),
]
