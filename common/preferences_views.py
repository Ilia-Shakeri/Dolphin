"""`/api/v1/preferences/` — the signed-in user's own panel preferences.

No feature gate and no role check beyond "signed in", and both absences are
deliberate. A feature gate answers "does this deployment have X"; a role
check answers "may this person do X to the business". Choosing your own
typeface is neither — it is the account owner's, the way their password and
their active sessions already are, and there is no deployment for which
"this customer did not license font size" is a sensible sentence.

What *is* enforced is that it can only ever be your own:
`common.preferences.update_preferences` takes an `actor` and no `user`, so
there is no parameter a request could supply to reach somebody else's row.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common import preferences
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.serializers import UserPreferenceUpdateSerializer
from common.throttles import SensitiveRateThrottle


class UserPreferenceView(APIView):
    """GET returns the effective preferences plus the choice catalog the
    settings page renders; POST saves whichever of them were sent.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    def _respond(self, request):
        data = dict(preferences.effective_preferences(request.user))
        data["catalog"] = preferences.catalog()
        data["currency_label"] = preferences.currency_label(data["currency_unit"])
        response = Response(data)
        # Private by definition, and wrong for any other reader — the same
        # header every other per-user endpoint in this codebase sets.
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description=(
            "The signed-in user's panel preferences — typeface, scale, currency unit and colour theme — "
            "plus the catalog of choices each one accepts."
        ),
    )
    def get(self, request):
        return self._respond(request)

    @extend_schema(
        request=UserPreferenceUpdateSerializer,
        responses={
            200: {"type": "object"},
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description="Saves the signed-in user's own preferences. Every field is independent and optional.",
    )
    def post(self, request):
        serializer = UserPreferenceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        preferences.update_preferences(
            actor=request.user,
            font_family=data.get("font_family"),
            font_scale=data.get("font_scale"),
            currency_unit=data.get("currency_unit"),
            theme=data.get("theme"),
        )
        return self._respond(request)
