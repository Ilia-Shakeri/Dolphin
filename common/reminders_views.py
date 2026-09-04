"""The topbar bell's API: what is due, and how much of it there is.

Two endpoints rather than one, for the same reason `chat` has a separate
`unread-count`: every open tab polls the badge on a timer, and making that
poll build and serialise every row it is not going to show would be real,
avoidable load on every page of every session. The panel opens the full list
only when someone actually clicks the bell.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from common import reminders
from common.openapi import ACCESS_DENIED_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated


class ReminderAccessMixin(FeatureGatedAPIMixin):
    """Ordinary authenticated reads — deliberately *not* throttled.

    These carried `SensitiveRateThrottle` in a first cut and it was wrong, in
    a way the suite caught immediately: `sensitive` is one shared 30/min
    bucket per user across every view that names it, and the badge here is
    polled on *every page load* plus once a minute after that. A user simply
    working quickly through the panel drained the bucket, and the next
    genuinely sensitive action — somebody else's write, on a different
    endpoint entirely — answered 429 for a reason nothing on their screen
    could explain.

    A rate limit protects something scarce or costly. This reads four
    indexed columns and returns rows the caller can already open by hand on
    the pages they came from, exactly like every other list endpoint in the
    panel, none of which is throttled either.
    """

    required_feature = "reminders"
    permission_classes = [IsActiveAuthenticated]


class ReminderListView(ReminderAccessMixin, APIView):
    """`/api/v1/reminders/` — everything due for the caller, grouped."""

    @extend_schema(
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE},
        description=(
            "Lead follow-ups and after-sales appointments that are overdue or fall today, plus cheques and "
            "instalments due within the next week. Each group is limited to the most urgent rows; `count` "
            "reports the true total. Only groups the deployment's features and the caller's own scope allow "
            "are present."
        ),
    )
    def get(self, request):
        response = Response(reminders.reminders_for(request.user))
        # Private and never cached: this is one user's own work queue, and it
        # changes the moment they act on it.
        response["Cache-Control"] = "private, no-store"
        return response


class ReminderCountView(ReminderAccessMixin, APIView):
    """`/api/v1/reminders/count/` — the badge number, polled."""

    @extend_schema(
        responses={
            200: {"type": "object", "properties": {"count": {"type": "integer"}}},
            403: ACCESS_DENIED_RESPONSE,
        },
        description="How many items are due for the caller, across every enabled source.",
    )
    def get(self, request):
        response = Response({"count": reminders.reminder_count_for(request.user)})
        response["Cache-Control"] = "private, no-store"
        return response
