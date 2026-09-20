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


class AvatarStateSerializer(serializers.Serializer):
    has_avatar = serializers.BooleanField()
    #: Where to fetch it. Always present — it is the cartoon's static URL
    #: when nothing has been uploaded — so the panel never has to decide
    #: which of two URLs to use.
    url = serializers.CharField()


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
        stored = avatars.has_avatar(target)
        url = (
            f"/api/v1/users/{target.pk}/avatar/image/"
            if stored
            else (avatars.default_avatar_url(target) or "")
        )
        return Response(AvatarStateSerializer({"has_avatar": stored, "url": url}).data)

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
        return Response(AvatarStateSerializer({
            "has_avatar": True,
            "url": f"/api/v1/users/{target.pk}/avatar/image/",
        }).data)

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
        return Response(AvatarStateSerializer({
            "has_avatar": False,
            "url": avatars.default_avatar_url(target) or "",
        }).data)


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
