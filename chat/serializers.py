from rest_framework import serializers

from chat.models import ChatMessage, ChatThread
from chat.selectors import unread_count_for
from common.ui_views import ROLE_LABELS


class ChatPeerSerializer(serializers.Serializer):
    """The other participant of a direct thread, from one viewer's side."""

    id = serializers.IntegerField()
    display_name = serializers.CharField()
    role_label = serializers.CharField()


class ChatThreadSerializer(serializers.Serializer):
    """One thread in "my conversations" — never the messages themselves.

    Built from a plain dict the view assembles (`peer`, `last_message_*`,
    `unread_count` each need the *viewer*, which a `ModelSerializer` over
    `ChatThread` alone has no way to see), not from the model instance
    directly — the same reason `common/serializers.py`'s `BrandSettingsSerializer`
    exists instead of exposing the model as-is.
    """

    id = serializers.IntegerField()
    peer = ChatPeerSerializer()
    last_message_body = serializers.CharField(allow_null=True)
    last_message_at = serializers.DateTimeField(allow_null=True)
    unread_count = serializers.IntegerField()


class ChatMessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.IntegerField(source="sender.pk")
    sender_display_name = serializers.SerializerMethodField()
    mine = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ("id", "thread_id", "sender_id", "sender_display_name", "mine", "body", "created_at")

    def get_sender_display_name(self, obj) -> str:
        return obj.sender.get_full_name() or obj.sender.username

    def get_mine(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and obj.sender_id == request.user.pk)


class ChatMessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(trim_whitespace=False)


class ChatStartThreadSerializer(serializers.Serializer):
    other_user_id = serializers.IntegerField()


def serialize_thread(thread, *, viewer):
    """Build the plain dict `ChatThreadSerializer` reads, from one viewer's side."""
    peer = next(p.user for p in thread.participants.select_related("user").all() if p.user_id != viewer.pk)
    last_message = thread.messages.order_by("-created_at", "-id").first()
    return {
        "id": thread.pk,
        "peer": {
            "id": peer.pk,
            "display_name": peer.get_full_name() or peer.username,
            "role_label": ROLE_LABELS.get(peer.role, peer.role),
        },
        "last_message_body": last_message.body if last_message else None,
        "last_message_at": thread.last_message_at,
        "unread_count": unread_count_for(viewer, thread.pk),
    }
