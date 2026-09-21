"""Uploading, serving and clearing one person's profile picture.

Three endpoints and one rule between them: who may change whose picture is
decided in `accounts.avatars`, not here, so a management command or a script
comes through the same gate a request does. These views add what only a view
can — the multipart parsing, the caching headers, and the 404 that keeps a
missing picture indistinguishable from a person who has none.
"""

from django.http import Http404, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import avatars
from accounts.models import User
from common.openapi import (
    ACCESS_DENIED_RESPONSE,
    NOT_FOUND_RESPONSE,
    THROTTLED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from common.permissions import IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle


class AvatarUploadSerializer(serializers.Serializer):
    """Only the file. Everything about it is checked in the service.

    `required=True` on purpose: an upload endpoint that accepts an empty body
    and does nothing is an endpoint that reports success for a failed pick.
    """

    avatar = serializers.FileField()


class AvatarDefaultChoiceSerializer(serializers.Serializer):
    """Which shipped cartoon to use — a filename from `/avatar-defaults/`."""

    name = serializers.CharField()


class AvatarStateSerializer(serializers.Serializer):
    has_avatar = serializers.BooleanField()
    #: Where to fetch it. Always present — it is the cartoon's static URL
    #: when nothing has been uploaded — so the panel never has to decide
    #: which of two URLs to use.
    url = serializers.CharField()
    #: The explicitly-picked cartoon's filename, or "" when this person has
    #: never picked one (still on the hash-derived default, or has an
    #: upload). The picker gallery uses this to highlight the active tile —
    #: without it, reopening the dialog could not tell "the cartoon showing"
    #: apart from "the cartoon that happens to render the same".
    chosen_default_name = serializers.CharField()


class AvatarDefaultsSerializer(serializers.Serializer):
    name = serializers.CharField()
    url = serializers.CharField()


def _state(target):
    """The full picture state for `target`, used by every endpoint below that
    changes or reports it — one place computing the three facts together so
    they cannot drift out of sync with each other.
    """
    stored = avatars.has_avatar(target)
    url = (
        f"/api/v1/users/{target.pk}/avatar/image/"
        if stored
        else (avatars.default_avatar_url(target) or "")
    )
    return {
        "has_avatar": stored,
        "url": url,
        "chosen_default_name": avatars.chosen_default_avatar_for(target) or "",
    }


def _target(request, user_id):
    """The user whose picture this is about.

    `None` means the caller themselves, which is the common case and the one
    every role may do. A numeric id is resolved here and authorised in the
    service, not by this lookup: finding a user is not permission to change
    their face.
    """
    if user_id is None:
        return request.user
    target = User.objects.filter(pk=user_id).first()
    if target is None:
        raise Http404()
    return target


class UserAvatarView(APIView):
    """`/api/v1/users/<id>/avatar/` and `/api/v1/profile/avatar/`."""

    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]
    parser_classes = [MultiPartParser]

    @extend_schema(
        responses={
            200: AvatarStateSerializer,
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Whether this person has uploaded a picture, and the URL to show for "
            "them either way — their own upload, or the Metronic cartoon derived "
            "from their id."
        ),
    )
    def get(self, request, user_id=None):
        target = _target(request, user_id)
        return Response(AvatarStateSerializer(_state(target)).data)

    @extend_schema(
        request=AvatarUploadSerializer,
        responses={
            200: AvatarStateSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Stores a profile picture. The panel crops and resizes before sending; "
            "this still re-checks the size and sniffs the real type from the file's "
            "own first bytes rather than trusting the declared content type."
        ),
    )
    def post(self, request, user_id=None):
        target = _target(request, user_id)
        form = AvatarUploadSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        upload = form.validated_data["avatar"]
        avatars.set_avatar(
            actor=request.user,
            target=target,
            content=upload.read(),
            original_filename=getattr(upload, "name", ""),
        )
        return Response(AvatarStateSerializer(_state(target)).data)

    @extend_schema(
        responses={
            200: AvatarStateSerializer,
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description="Removes the stored picture, so the cartoon comes back.",
    )
    def delete(self, request, user_id=None):
        target = _target(request, user_id)
        avatars.clear_avatar(actor=request.user, target=target)
        return Response(AvatarStateSerializer(_state(target)).data)


class UserAvatarDefaultsView(APIView):
    """`/api/v1/avatar-defaults/` — the gallery the picker modal fills itself
    from, rather than the panel hardcoding a list of 52 filenames that would
    fall behind the moment this build's own static set does.
    """

    permission_classes = [IsActiveAuthenticated]

    @extend_schema(
        responses={200: AvatarDefaultsSerializer(many=True)},
        description="Every default cartoon this build ships, as {name, url}.",
    )
    def get(self, request):
        return Response(AvatarDefaultsSerializer(avatars.default_avatar_choices(), many=True).data)


class UserAvatarDefaultChoiceView(APIView):
    """`/api/v1/users/<id>/avatar/default/` and `/api/v1/profile/avatar/default/`
    — pick one of the shipped cartoons instead of the hash-derived one.
    """

    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    @extend_schema(
        request=AvatarDefaultChoiceSerializer,
        responses={
            200: AvatarStateSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Picks one of the shipped cartoons as this person's picture, "
            "replacing any uploaded one — an upload always wins over a "
            "default while both exist, so a pick made on top of an upload "
            "would otherwise have no visible effect."
        ),
    )
    def post(self, request, user_id=None):
        target = _target(request, user_id)
        form = AvatarDefaultChoiceSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        avatars.set_default_avatar_choice(
            actor=request.user, target=target, name=form.validated_data["name"]
        )
        return Response(AvatarStateSerializer(_state(target)).data)


class UserAvatarImageView(APIView):
    """`/api/v1/users/<id>/avatar/image/` — the bytes themselves.

    Authenticated, unlike the panel logo: a logo is what an unauthenticated
    login page shows, a colleague's face is not. Any signed-in member of this
    deployment may see it — the same people who already see that person's
    name on every lead and every sale.
    """

    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    @extend_schema(
        responses={
            (200, "image/*"): OpenApiResponse(
                response=OpenApiTypes.BINARY, description="The stored picture."
            ),
            (403, "application/json"): ACCESS_DENIED_RESPONSE,
            (404, "application/json"): NOT_FOUND_RESPONSE,
            (429, "application/json"): THROTTLED_RESPONSE,
        },
        description="Streams the stored picture, or 404 when this person has none.",
    )
    def get(self, request, user_id):
        row = avatars.avatar_for(User.objects.filter(pk=user_id).first())
        if row is None:
            # The same 404 a missing user gets: whether a particular id
            # exists is not something this endpoint should answer.
            raise Http404()
        response = HttpResponse(bytes(row.content), content_type=row.content_type)
        # Private, and short: it changes the moment someone uploads a new
        # one, and the URL does not change with it. The panel cache-busts
        # with `?v=` after an upload, the same way the brand logo does.
        response["Cache-Control"] = "private, max-age=300"
        response["X-Content-Type-Options"] = "nosniff"
        return response
