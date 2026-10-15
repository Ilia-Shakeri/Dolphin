"""`/api/v1/custom-fields/` (2.40.53): the company's own fields.

404 without the `customization` feature (a module a deployment does not run
looks like one never built); then `customization.manage`, checked again by the
service. Reading the active fields of an entity is open to anyone who may use
the panel — every form that offers them needs them — but the pages embed them
already, so this is mostly the settings tab's own list.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from common.openapi import ACCESS_DENIED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, HasCapabilityForMethod, IsActiveAuthenticated
from common.serializers import RejectServerFieldsMixin
from common.throttles import SensitiveRateThrottle
from customization import services
from customization.models import CustomFieldDefinition


class DefinitionWriteSerializer(RejectServerFieldsMixin, serializers.Serializer):
    entity = serializers.CharField(required=False)
    label = serializers.CharField(required=False, allow_blank=True)
    field_type = serializers.CharField(required=False)
    choices = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)
    required = serializers.BooleanField(required=False)
    show_in_list = serializers.BooleanField(required=False)
    filterable = serializers.BooleanField(required=False)
    searchable = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)


class MoveSerializer(RejectServerFieldsMixin, serializers.Serializer):
    direction = serializers.ChoiceField(choices=["up", "down"])


class CustomFieldAccessMixin(FeatureGatedAPIMixin):
    required_feature = services.FEATURE
    required_capabilities = (services.CAPABILITY,)
    permission_classes = [IsActiveAuthenticated, HasCapabilityForMethod]

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.request.method not in ("GET", "HEAD", "OPTIONS"):
            throttles.append(SensitiveRateThrottle())
        return throttles


def _listing():
    return {
        "entities": [{"value": value, "label": label} for value, label in CustomFieldDefinition.Entity.choices],
        "field_types": [{"value": value, "label": label} for value, label in CustomFieldDefinition.FieldType.choices],
        "fields": [
            services.serialize_definition(definition)
            for definition in CustomFieldDefinition.objects.order_by("entity", "position", "id")
        ],
    }


class CustomFieldListView(CustomFieldAccessMixin, APIView):
    @extend_schema(responses={200: dict, 403: ACCESS_DENIED_RESPONSE}, description="Every custom field, active or not.")
    def get(self, request):
        return Response(_listing())

    @extend_schema(
        request=DefinitionWriteSerializer, responses={201: dict, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE},
        description="Adds a field to an entity; its key is made by the server and never changes.",
    )
    def post(self, request):
        serializer = DefinitionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("is_active", None)
        services.create_definition(
            actor=request.user, entity=data.pop("entity", "customer"), label=data.pop("label", ""),
            field_type=data.pop("field_type", ""), choices=data.pop("choices", None), **data,
        )
        return Response(_listing(), status=201)


class OneDefinitionMixin(CustomFieldAccessMixin):
    def _definition(self, pk):
        definition = CustomFieldDefinition.objects.filter(pk=pk).first()
        if definition is None:
            raise NotFound()
        return definition


class CustomFieldDetailView(OneDefinitionMixin, APIView):

    @extend_schema(
        request=DefinitionWriteSerializer, responses={200: dict, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE},
        description="Changes the label, the choices, the four flags or whether it is active. The type never changes.",
    )
    def patch(self, request, pk):
        serializer = DefinitionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("entity", None)
        data.pop("field_type", None)
        services.update_definition(actor=request.user, definition=self._definition(pk), **data)
        return Response(_listing())


class CustomFieldMoveView(OneDefinitionMixin, APIView):
    @extend_schema(request=MoveSerializer, responses={200: dict, 403: ACCESS_DENIED_RESPONSE}, description="One place up or down.")
    def post(self, request, pk):
        serializer = MoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.move_definition(actor=request.user, definition=self._definition(pk), direction=serializer.validated_data["direction"])
        return Response(_listing())
