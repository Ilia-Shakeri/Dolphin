"""`/api/v1/profiles/<type>/<id>/timeline/` — one timeline endpoint for every
person type (2.19.0).

The profile page's «فعالیت‌ها» tab and its overview's «آخرین رویدادها» read
this. For a customer it answers exactly what `/api/v1/customers/<id>/timeline/`
does (and stays behind the same `customer_timeline` feature); for a user it
is `profiles.user_timeline`. A person outside the caller's scope is a 404.
"""

from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from common.deployment.profile import feature_enabled
from common.openapi import ACCESS_DENIED_RESPONSE
from common.permissions import IsActiveAuthenticated
from profiles.registry import resolve_person

#: Feature each type's timeline needs beyond the type's own.
TIMELINE_FEATURE = {"customer": "customer_timeline"}


class PersonTimelineView(APIView):
    permission_classes = [IsActiveAuthenticated]

    @extend_schema(
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 404: None},
        description=(
            "Events about one person, newest first, in the shape of the customer timeline: `count` found and "
            "`events` shown. `person_type` is `customer` or `user`. Only the sources this deployment's features "
            "and the caller's own scope allow are present; a person outside the caller's scope is a 404."
        ),
    )
    def get(self, request, person_type, person_id):
        adapter, person = resolve_person(request.user, person_type, person_id)
        if adapter is None:
            raise Http404()
        for feature in (adapter.required_feature, TIMELINE_FEATURE.get(person_type)):
            if feature and not feature_enabled(feature):
                raise Http404()
        if person is None:
            raise Http404()
        payload = adapter.timeline(request.user, person)
        limit = request.query_params.get("limit")
        if limit and limit.isdigit():
            payload = {**payload, "events": payload["events"][: max(1, int(limit))]}
        response = Response(payload)
        response["Cache-Control"] = "private, no-store"
        return response
