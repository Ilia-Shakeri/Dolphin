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


def _visible_or_404(request, person_type, person_id):
    adapter, person = resolve_person(request.user, person_type, person_id)
    if adapter is None or person is None:
        raise Http404()
    if adapter.required_feature and not feature_enabled(adapter.required_feature):
        raise Http404()
    return adapter, person


class PersonCardsView(APIView):
    """`GET profiles/<type>/<id>/cards/?period=this_month` — the header's
    stat cards #4–#7, only the ones this caller may see (2.20.0)."""

    permission_classes = [IsActiveAuthenticated]

    @extend_schema(
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 404: None},
        description=(
            "The stat cards visible to the caller on one person's profile, each `{key, label, slot, value, raw, "
            "missing, tooltip, accent, trend}` for the chosen `period` (`this_month`, `last_month`, "
            "`last_90_days`, `this_year`; Jalali months). A card the caller may not see is absent, not empty."
        ),
    )
    def get(self, request, person_type, person_id):
        from profiles.cards import PERIODS, card_values, period_for

        _, person = _visible_or_404(request, person_type, person_id)
        period = period_for(request.query_params.get("period", ""))
        response = Response({
            "period": {"key": period.key, "label": period.label, "start": period.start.isoformat(), "end": period.end.isoformat()},
            "periods": [{"key": key, "label": label} for key, label in PERIODS],
            "cards": card_values(request.user, person_type, person, period),
        })
        response["Cache-Control"] = "private, no-store"
        return response


class PersonScoreView(APIView):
    """`GET profiles/<type>/<id>/score/` — the current score, why, and its history."""

    permission_classes = [IsActiveAuthenticated]

    @extend_schema(
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 404: None},
        description=(
            "The person's current score (recomputed first when a day old), its per-factor breakdown with the "
            "reason for each, and up to thirty earlier snapshots. 404 when scoring is off, the person is outside "
            "the caller's scope, or the caller may not see this person's score."
        ),
    )
    def get(self, request, person_type, person_id):
        from profiles.cards import cards_for
        from scoring.services import LEVEL_LABELS, current_score, history

        if not feature_enabled("person_scoring"):
            raise Http404()
        _, person = _visible_or_404(request, person_type, person_id)
        if not any(card.key == "score" for card in cards_for(request.user, person_type, person)):
            raise Http404()
        snapshot = current_score(person_type, person)

        def serialize(row):
            label, accent = LEVEL_LABELS.get(row.level, ("", ""))
            return {"score": row.score, "level": row.level, "level_label": label, "accent": accent, "computed_at": row.computed_at.isoformat()}

        response = Response({
            "current": {**serialize(snapshot), "breakdown": snapshot.breakdown} if snapshot else None,
            "history": [serialize(row) for row in history(person_type, person.pk)],
        })
        response["Cache-Control"] = "private, no-store"
        return response


class PersonAnalysisView(APIView):
    """`GET profiles/customer/<id>/analysis/` — the customer «تحلیل» tab (2.33.0)."""

    permission_classes = [IsActiveAuthenticated]

    @extend_schema(
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 404: None},
        description=(
            "Five figures (`total_purchase`, `total_received`, `debt_balance`, `open_installments`, `next_due`) "
            "and, for each that has one, a monthly `series` of `{label, value, display}` points. A figure the "
            "caller may not read is `missing` with the reason, never zero. Customers only; 404 for a customer "
            "outside the caller's scope or when the deployment has no invoices."
        ),
    )
    def get(self, request, person_type, person_id):
        from profiles.analysis import customer_analysis

        if person_type != "customer" or not feature_enabled("invoices"):
            raise Http404()
        _, person = _visible_or_404(request, person_type, person_id)
        payload = customer_analysis(request.user, person)
        response = Response(payload)
        response["Cache-Control"] = "private, no-store"
        return response
