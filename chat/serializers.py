from rest_framework import serializers

from chat.models import ChatMessage, ChatThread
from chat.selectors import last_messages_for, unread_count_for, unread_counts_for
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


def _peer_of(thread, *, viewer):
    # Deliberately `.all()` with nothing chained after it: that is the one
    # call form Django serves from `prefetch_related("participants__user")`'s
    # cache. `.select_related("user")` used to sit here too, which builds a
    # brand new queryset and so skips that cache — every thread re-querying
    # its own participants regardless of what the view had already fetched.
    return next(p.user for p in thread.participants.all() if p.user_id != viewer.pk)


def serialize_thread(thread, *, viewer):
    """Build the plain dict `ChatThreadSerializer` reads, from one viewer's side.

    For one thread — starting a new conversation returns exactly one. Listing
    "my conversations" wants `serialize_threads` below instead: this reaches
    the database twice on its own (the last message, the unread count), which
    is fine once and is not what a list of N should do N times over.
    """
    peer = _peer_of(thread, viewer=viewer)
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


def serialize_threads(threads, *, viewer):
    """`serialize_thread` for a whole list, in a fixed number of queries.

    `ChatThreadListView` is polled every eight seconds by every open tab;
    building each thread's dict independently cost that endpoint roughly
    `4N` queries for `N` conversations (one to re-fetch participants past the
    prefetch cache, one for the last message, two more for the unread count).
    This does the same assembly from `last_messages_for` and
    `unread_counts_for`'s bulk lookups — two more queries in total, not per
    thread — plus the view's own `prefetch_related("participants__user")`
    for the peer, so listing 1 conversation costs the same as listing 50.
    """
    threads = list(threads)
    thread_ids = [thread.pk for thread in threads]
    last_message_by_thread = last_messages_for(thread_ids)
    last_read_at_by_thread = {}
    for thread in threads:
        participant = next((p for p in thread.participants.all() if p.user_id == viewer.pk), None)
        last_read_at_by_thread[thread.pk] = participant.last_read_at if participant else None
    unread_count_by_thread = unread_counts_for(viewer, last_read_at_by_thread)

    rows = []
    for thread in threads:
        peer = _peer_of(thread, viewer=viewer)
        last_message = last_message_by_thread.get(thread.pk)
        rows.append({
            "id": thread.pk,
            "peer": {
                "id": peer.pk,
                "display_name": peer.get_full_name() or peer.username,
                "role_label": ROLE_LABELS.get(peer.role, peer.role),
            },
            "last_message_body": last_message.body if last_message else None,
            "last_message_at": thread.last_message_at,
            "unread_count": unread_count_by_thread.get(thread.pk, 0),
        })
    return rows
