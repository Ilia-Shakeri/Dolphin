from django.urls import path

from assistant.views import AssistantStatusView, AssistantSuggestView

urlpatterns = [
    path("assistant/suggest/", AssistantSuggestView.as_view(), name="assistant-suggest"),
    path("assistant/status/", AssistantStatusView.as_view(), name="assistant-status"),
]
