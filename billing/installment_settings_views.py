"""`/api/v1/installment-settings/` (2.40.51): this company's instalment rules.

404 unless at least one advanced instalment feature is enabled (a module a
deployment does not run looks like one never built); then the
`installments.configure` capability, checked again by the service.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from billing import installment_settings
from billing.serializers import InstallmentSettingsUpdateSerializer
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import HasCapabilityForMethod, IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle


class InstallmentSettingsView(APIView):
    permission_classes = [IsActiveAuthenticated, HasCapabilityForMethod]
    required_capabilities = (installment_settings.CAPABILITY,)

    def initial(self, request, *args, **kwargs):
        if not installment_settings.enabled_features():
            raise NotFound()
        super().initial(request, *args, **kwargs)

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.request.method == "PATCH":
            throttles.append(SensitiveRateThrottle())
        return throttles

    @extend_schema(responses={200: dict, 403: ACCESS_DENIED_RESPONSE}, description="The stored rules.")
    def get(self, request):
        response = Response(installment_settings.serialize(installment_settings.get_settings()))
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request=InstallmentSettingsUpdateSerializer,
        responses={200: dict, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description="Changes any of the rules; a field not sent stays as it is.",
    )
    def patch(self, request):
        serializer = InstallmentSettingsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = installment_settings.update_settings(actor=request.user, **serializer.validated_data)
        response = Response(installment_settings.serialize(row))
        response["Cache-Control"] = "private, no-store"
        return response
