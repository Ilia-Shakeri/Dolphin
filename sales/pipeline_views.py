"""`/api/v1/pipeline/` (2.40.57, BIZ-002): shaping the stage lists.

Settings → «شخصی‌سازی». 404 without the `customization` feature; then
`customization.manage`, checked again by `sales.pipeline`. Moving a lead or a
campaign person is not here — it is the record's own `stage/` action, under
the record's own permission and scope.
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
from sales import pipeline
from sales.models import LostReason, PipelineStage


class StageWriteSerializer(RejectServerFieldsMixin, serializers.Serializer):
    pipeline = serializers.CharField(required=False)
    label = serializers.CharField(required=False, allow_blank=True)
    qualifies = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)


class ReasonWriteSerializer(RejectServerFieldsMixin, serializers.Serializer):
    label = serializers.CharField(required=False, allow_blank=True)
    needs_note = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)


class PipelineMoveSerializer(RejectServerFieldsMixin, serializers.Serializer):
    #: «up» or «down», checked by `sales.pipeline`.
    direction = serializers.CharField(max_length=4)


class PipelineAccessMixin(FeatureGatedAPIMixin):
    required_feature = pipeline.CONFIGURE_FEATURE
    required_capabilities = (pipeline.CONFIGURE_CAPABILITY,)
    permission_classes = [IsActiveAuthenticated, HasCapabilityForMethod]

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.request.method not in ("GET", "HEAD", "OPTIONS"):
            throttles.append(SensitiveRateThrottle())
        return throttles

    @staticmethod
    def _one(model, pk):
        item = model.objects.filter(pk=pk).first()
        if item is None:
            raise NotFound()
        return item


class PipelineView(PipelineAccessMixin, APIView):
    @extend_schema(responses={200: dict, 403: ACCESS_DENIED_RESPONSE},
                   description="Both stage workflows and the lost reasons, on or off.")
    def get(self, request):
        return Response(pipeline.pipeline_payload())


class PipelineStageListView(PipelineAccessMixin, APIView):
    @extend_schema(request=StageWriteSerializer,
                   responses={201: dict, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE},
                   description="Adds an open stage after the last open one; its key is made by the server.")
    def post(self, request):
        body = StageWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        pipeline.create_stage(
            actor=request.user, pipeline=data.get("pipeline", ""), label=data.get("label", ""),
            qualifies=data.get("qualifies", False),
        )
        return Response(pipeline.pipeline_payload(), status=201)


class PipelineStageDetailView(PipelineAccessMixin, APIView):
    @extend_schema(request=StageWriteSerializer,
                   responses={200: dict, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE})
    def patch(self, request, pk):
        body = StageWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        changes = dict(body.validated_data)
        changes.pop("pipeline", None)
        pipeline.update_stage(actor=request.user, stage=self._one(PipelineStage, pk), **changes)
        return Response(pipeline.pipeline_payload())


class PipelineStageMoveView(PipelineAccessMixin, APIView):
    @extend_schema(request=PipelineMoveSerializer, responses={200: dict, 400: VALIDATION_ERROR_RESPONSE})
    def post(self, request, pk):
        body = PipelineMoveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        pipeline.move_stage(actor=request.user, stage=self._one(PipelineStage, pk), **body.validated_data)
        return Response(pipeline.pipeline_payload())


class LostReasonListView(PipelineAccessMixin, APIView):
    @extend_schema(request=ReasonWriteSerializer,
                   responses={201: dict, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE},
                   description="Adds a lost reason before «سایر».")
    def post(self, request):
        body = ReasonWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        pipeline.create_lost_reason(
            actor=request.user, label=data.get("label", ""), needs_note=data.get("needs_note", False),
        )
        return Response(pipeline.pipeline_payload(), status=201)


class LostReasonDetailView(PipelineAccessMixin, APIView):
    @extend_schema(request=ReasonWriteSerializer,
                   responses={200: dict, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE})
    def patch(self, request, pk):
        body = ReasonWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        pipeline.update_lost_reason(actor=request.user, reason=self._one(LostReason, pk), **body.validated_data)
        return Response(pipeline.pipeline_payload())


class LostReasonMoveView(PipelineAccessMixin, APIView):
    @extend_schema(request=PipelineMoveSerializer, responses={200: dict, 400: VALIDATION_ERROR_RESPONSE})
    def post(self, request, pk):
        body = PipelineMoveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        pipeline.move_lost_reason(actor=request.user, reason=self._one(LostReason, pk), **body.validated_data)
        return Response(pipeline.pipeline_payload())
