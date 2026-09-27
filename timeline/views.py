"""Profile notes over the API (2.20.0).

`GET/POST /api/v1/profiles/<type>/<id>/notes/` lists and adds notes on one
person; `PATCH/DELETE /api/v1/person-notes/<id>/` edits (author only) or
removes one (Platform Admin, or `notes.delete`). A person the caller may not
see is a 404 everywhere, the same as every other direct read.
"""

from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import can_delete
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated
from common.serializers import RejectServerFieldsMixin
from common.throttles import SensitiveRateThrottle
from profiles.registry import resolve_person
from timeline.models import NOTE_MAX_LENGTH, PersonNote
from timeline.selectors import notes_for
from timeline.services import NOTE_DELETE, add_note, delete_note, update_note


class PersonNoteSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"person_type", "person_id", "author", "author_display", "can_edit", "can_delete", "created_at", "updated_at"}
    body = serializers.CharField(max_length=NOTE_MAX_LENGTH, trim_whitespace=True)
    author_display = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = PersonNote
        fields = ["id", "person_type", "person_id", "body", "author", "author_display", "can_edit", "can_delete", "created_at", "updated_at"]
        read_only_fields = ["id", "person_type", "person_id", "author", "author_display", "can_edit", "can_delete", "created_at", "updated_at"]

    def get_author_display(self, note) -> str:
        return note.author.get_full_name() or note.author.username

    def get_can_edit(self, note) -> bool:
        return note.author_id == self.context["request"].user.pk

    def get_can_delete(self, note) -> bool:
        return can_delete(self.context["request"].user, NOTE_DELETE)


def _person_or_404(request, person_type, person_id):
    adapter, person = resolve_person(request.user, person_type, person_id)
    if adapter is None or person is None:
        raise Http404()
    return person


class PersonNotesView(FeatureGatedAPIMixin, APIView):
    required_feature = "person_notes"
    permission_classes = [IsActiveAuthenticated]

    def get_throttles(self):
        return [SensitiveRateThrottle()] if self.request.method == "POST" else super().get_throttles()

    @extend_schema(responses={200: PersonNoteSerializer(many=True), 403: ACCESS_DENIED_RESPONSE, 404: None})
    def get(self, request, person_type, person_id):
        _person_or_404(request, person_type, person_id)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(notes_for(request.user, person_type, person_id), request, view=self)
        return paginator.get_paginated_response(
            PersonNoteSerializer(page, many=True, context={"request": request}).data
        )

    @extend_schema(
        request=PersonNoteSerializer,
        responses={201: PersonNoteSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 404: None, 429: THROTTLED_RESPONSE},
    )
    def post(self, request, person_type, person_id):
        _person_or_404(request, person_type, person_id)
        serializer = PersonNoteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        note = add_note(actor=request.user, person_type=person_type, person_id=person_id, body=serializer.validated_data["body"])
        return Response(PersonNoteSerializer(note, context={"request": request}).data, status=status.HTTP_201_CREATED)


class PersonNoteDetailView(FeatureGatedAPIMixin, APIView):
    required_feature = "person_notes"
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    def _note(self, request, note_id):
        note = PersonNote.objects.select_related("author").filter(pk=note_id).first()
        if note is None:
            raise Http404()
        _person_or_404(request, note.person_type, note.person_id)
        if not notes_for(request.user, note.person_type, note.person_id).filter(pk=note.pk).exists():
            raise Http404()
        return note

    @extend_schema(
        request=PersonNoteSerializer,
        responses={200: PersonNoteSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 404: None, 429: THROTTLED_RESPONSE},
    )
    def patch(self, request, note_id):
        note = self._note(request, note_id)
        serializer = PersonNoteSerializer(note, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        note = update_note(actor=request.user, note=note, body=serializer.validated_data.get("body", note.body))
        return Response(PersonNoteSerializer(note, context={"request": request}).data)

    @extend_schema(responses={204: None, 403: ACCESS_DENIED_RESPONSE, 404: None, 429: THROTTLED_RESPONSE})
    def delete(self, request, note_id):
        note = self._note(request, note_id)
        delete_note(actor=request.user, note=note)
        return Response(status=status.HTTP_204_NO_CONTENT)
