from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import crm_identities
from chat import services
from chat.selectors import is_participant, messages_for, threads_for, total_unread_count
from chat.serializers import (
    ChatMessageCreateSerializer,
    ChatMessageSerializer,
    ChatStartThreadSerializer,
    ChatThreadSerializer,
    serialize_thread,
)
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle
from common.ui_views import ROLE_LABELS

#: A page of messages, oldest of the page first (so the client appends
#: straight onto the bottom of the scroll region without re-sorting), newest
#: page by default. Small on purpose — this is a coordination side-channel,
#: not an archive browser.
MESSAGE_PAGE_SIZE = 50

#: How many colleagues the "start a new conversation" picker offers before a
#: real search box would be worth building. Deployments run a handful of
#: named seats (BACKEND_SPEC.md's own capacity framing), not hundreds.
COLLEAGUE_LIST_LIMIT = 200


class ChatAccessMixin(FeatureGatedAPIMixin):
    required_feature = "internal_chat"
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]


class ChatThreadListView(ChatAccessMixin, APIView):
    """`/api/v1/chat/threads/` — my conversations; POST starts or reuses one."""

    @extend_schema(
        responses={200: ChatThreadSerializer(many=True), 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description="Every direct thread the caller participates in, most recent activity first.",
    )
    def get(self, request):
        threads = threads_for(request.user).prefetch_related("participants__user")
        data = [serialize_thread(thread, viewer=request.user) for thread in threads]
        response = Response(data)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request=ChatStartThreadSerializer,
        responses={
            200: ChatThreadSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description="Returns the existing direct thread with this colleague, creating one if none exists yet.",
    )
    def post(self, request):
        serializer = ChatStartThreadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        thread = services.get_or_create_direct_thread(
            actor=request.user, other_user_id=serializer.validated_data["other_user_id"],
        )
        response = Response(serialize_thread(thread, viewer=request.user))
        response["Cache-Control"] = "private, no-store"
        return response


class ChatMessageListView(ChatAccessMixin, APIView):
    """`/api/v1/chat/threads/<id>/messages/` — read a page, or send one.

    A `GET` also marks the thread read for the caller: opening a
    conversation is what "read" means here, the same as the topbar's
    activity-log bell needs no separate "mark as read" click either.
    """

    @extend_schema(
        responses={
            200: ChatMessageSerializer(many=True),
            403: ACCESS_DENIED_RESPONSE,
            404: None,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Up to the most recent 50 messages, oldest first. `?before_id=<id>` pages further back for the "
            "same thread. `?after_id=<id>` returns only messages newer than that id, for polling — neither "
            "marks the thread read, only a plain `GET` does."
        ),
    )
    def get(self, request, thread_id):
        # A thread outside the caller's own membership is a 404, not a 403 or
        # a silently-empty page — same as `AttachmentDownloadView`'s direct-id
        # read: it must not reveal whether the thread exists at all.
        if not is_participant(request.user, thread_id):
            from django.http import Http404

            raise Http404()
        queryset = messages_for(request.user, thread_id)
        before_id = request.query_params.get("before_id")
        after_id = request.query_params.get("after_id")
        polling = bool(after_id)
        if before_id:
            queryset = queryset.filter(pk__lt=before_id).order_by("-created_at", "-id")[:MESSAGE_PAGE_SIZE]
            messages = list(reversed(queryset))
        elif after_id:
            messages = list(queryset.filter(pk__gt=after_id).order_by("created_at", "id"))
        else:
            queryset = queryset.order_by("-created_at", "-id")[:MESSAGE_PAGE_SIZE]
            messages = list(reversed(queryset))
        if not polling:
            services.mark_thread_read(actor=request.user, thread_id=thread_id)
        data = ChatMessageSerializer(messages, many=True, context={"request": request}).data
        response = Response(data)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request=ChatMessageCreateSerializer,
        responses={
            201: ChatMessageSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description="Sends one message into a thread the caller participates in.",
    )
    def post(self, request, thread_id):
        serializer = ChatMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = services.send_message(
            actor=request.user, thread_id=thread_id, body=serializer.validated_data["body"],
        )
        data = ChatMessageSerializer(message, context={"request": request}).data
        response = Response(data, status=201)
        response["Cache-Control"] = "private, no-store"
        return response


class ChatThreadReadView(ChatAccessMixin, APIView):
    """`/api/v1/chat/threads/<id>/read/` — mark read without paging messages.

    The polling loop already has every message it needs from
    `ChatMessageListView`'s `after_id`; asking it to re-fetch a full page of
    up to 50 messages just to get the read-marking side effect would be
    real, avoidable load on every open tab, every four seconds.
    """

    @extend_schema(
        # "Read up to now" carries no body — the thread is in the URL and the
        # timestamp is the server's. Declared for the same reason as
        # `AttachmentDeleteView`: without it the generator tries to guess a
        # request serializer for a write method and fails.
        request=None,
        responses={204: None, 403: ACCESS_DENIED_RESPONSE, 404: None, 429: THROTTLED_RESPONSE},
        description="Marks the thread read for the caller as of now.",
    )
    def post(self, request, thread_id):
        if not is_participant(request.user, thread_id):
            from django.http import Http404

            raise Http404()
        services.mark_thread_read(actor=request.user, thread_id=thread_id)
        return Response(status=204)


class ChatUnreadCountView(ChatAccessMixin, APIView):
    """`/api/v1/chat/unread-count/` — the topbar badge, polled."""

    @extend_schema(
        responses={200: {"type": "object", "properties": {"count": {"type": "integer"}}}},
        description="Unread messages across every thread the caller participates in.",
    )
    def get(self, request):
        response = Response({"count": total_unread_count(request.user)})
        response["Cache-Control"] = "private, no-store"
        return response


class ChatColleaguesView(ChatAccessMixin, APIView):
    """`/api/v1/chat/colleagues/` — who the "new conversation" picker offers."""

    @extend_schema(
        responses={200: {"type": "array", "items": {"type": "object"}}},
        description="Every other active, ordinary user of this deployment — chat has no role or workstream scope.",
    )
    def get(self, request):
        colleagues = (
            crm_identities()
            .exclude(pk=request.user.pk)
            .order_by("first_name", "last_name", "username")[:COLLEAGUE_LIST_LIMIT]
        )
        data = [
            {
                "id": user.pk,
                "display_name": user.get_full_name() or user.username,
                "role_label": ROLE_LABELS.get(user.role, user.role),
            }
            for user in colleagues
        ]
        response = Response(data)
        response["Cache-Control"] = "private, no-store"
        return response
