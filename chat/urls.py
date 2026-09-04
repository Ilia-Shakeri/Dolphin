from django.urls import path

from chat.views import (
    ChatColleaguesView,
    ChatMessageListView,
    ChatThreadListView,
    ChatThreadReadView,
    ChatUnreadCountView,
)

urlpatterns = [
    path("chat/threads/", ChatThreadListView.as_view(), name="chat-threads"),
    path("chat/threads/<int:thread_id>/messages/", ChatMessageListView.as_view(), name="chat-messages"),
    path("chat/threads/<int:thread_id>/read/", ChatThreadReadView.as_view(), name="chat-thread-read"),
    path("chat/unread-count/", ChatUnreadCountView.as_view(), name="chat-unread-count"),
    path("chat/colleagues/", ChatColleaguesView.as_view(), name="chat-colleagues"),
]
