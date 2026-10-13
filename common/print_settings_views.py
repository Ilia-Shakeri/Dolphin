"""The print layout API (2.40.44): the settings page reads and writes here.

`GET/POST /api/v1/print-settings/` — the stored choices (`common.print_settings`);
`GET /api/v1/print-settings/<logo|stamp>/` — one stored image, for the settings
page's own preview. Feature `print_customization` (404 without it, like every
gated module) and capability `print_settings.manage`, re-checked by the service.
"""

from django.http import Http404, HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from common import print_settings
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, HasCapabilityForMethod, IsActiveAuthenticated
from common.serializers import PrintSettingsSerializer, PrintSettingsUpdateSerializer
from common.throttles import SensitiveRateThrottle

FIELDS = ("accent_color", "tagline", "footer_text", "paper_size", "show_warehouse", "show_payment_summary", "show_issuer")


class PrintSettingsAccessMixin(FeatureGatedAPIMixin):
    required_feature = print_settings.FEATURE
    required_capabilities = (print_settings.CAPABILITY,)
    permission_classes = [IsActiveAuthenticated, HasCapabilityForMethod]


class PrintSettingsView(PrintSettingsAccessMixin, APIView):
    parser_classes = [MultiPartParser]
    throttle_classes = [SensitiveRateThrottle]

    @extend_schema(
        responses={200: PrintSettingsSerializer, 403: ACCESS_DENIED_RESPONSE},
        description="How printed documents look. Whether each image is set, never the image itself.",
    )
    def get(self, request):
        response = Response(PrintSettingsSerializer(print_settings.get_print_settings()).data)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request=PrintSettingsUpdateSerializer,
        responses={200: PrintSettingsSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE,
                   429: THROTTLED_RESPONSE},
        description=(
            "Changes any of the settings; a field not sent stays as it is. `logo`/`stamp` replace an image "
            "(jpeg, png or webp, at most 2 MB); `remove_logo`/`remove_stamp` clear one."
        ),
    )
    def post(self, request):
        serializer = PrintSettingsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Only what was sent: a multipart form reads an absent boolean as False.
        fields = {name: data[name] for name in FIELDS if name in request.data}
        images = {name: data[name].read() for name in print_settings.IMAGES if data.get(name) is not None}
        remove = [name for name in print_settings.IMAGES if data.get(f"remove_{name}")]
        row = print_settings.update_print_settings(actor=request.user, images=images, remove=remove, **fields)
        response = Response(PrintSettingsSerializer(row).data)
        response["Cache-Control"] = "private, no-store"
        return response


class PrintSettingsImageView(PrintSettingsAccessMixin, APIView):
    @extend_schema(
        responses={200: bytes, 404: None, 403: ACCESS_DENIED_RESPONSE},
        description="One stored image (`logo` or `stamp`), or 404 when it is not set.",
        operation_id="api_v1_print_settings_image_retrieve",
    )
    def get(self, request, image):
        if image not in print_settings.IMAGES:
            raise Http404()
        row = print_settings.get_print_settings()
        content = getattr(row, f"{image}_content")
        if content is None:
            raise Http404()
        response = HttpResponse(bytes(content), content_type=getattr(row, f"{image}_content_type"))
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
