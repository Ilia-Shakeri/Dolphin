from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.models import User
from aftersales.models import AfterSalesRequest
from aftersales.selectors import after_sales_requests_for
from aftersales.serializers import AfterSalesAssigneeSerializer, AfterSalesHistorySerializer, AfterSalesRequestSerializer, AssignmentSerializer, CloseSerializer, StatusTransitionSerializer
from aftersales.services import assign_after_sales_request, close_after_sales_request, transition_after_sales_status
from common.openapi import ACCESS_DENIED_RESPONSE, CONFLICT_RESPONSE, NOT_FOUND_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.throttles import SensitiveActionThrottleMixin
from common.viewsets import NoDestroyModelViewSet


ELEVATED = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}


class AfterSalesRequestViewSet(SensitiveActionThrottleMixin, NoDestroyModelViewSet):
    queryset = AfterSalesRequest.objects.none()
    serializer_class = AfterSalesRequestSerializer
    http_method_names = ["get", "post", "head", "options"]
    sensitive_actions = frozenset({"create", "assign", "transition_status", "close"})
    search_fields = ["subject", "customer__full_name", "status"]
    ordering_fields = ["created_at", "updated_at", "closed_at", "status"]
    list_query_parameters = {"status", "assigned_to", "is_closed"}
    action_query_parameters = {"history": {"page"}, "assignees": {"page"}}

    def get_queryset(self):
        queryset = after_sales_requests_for(self.request.user).select_related("customer", "sale", "document", "assigned_to", "created_by")
        status = self.request.query_params.get("status")
        if status is not None:
            queryset = queryset.filter(status=status)
        assigned_to = self.request.query_params.get("assigned_to")
        if assigned_to is not None:
            if not assigned_to.isdecimal() or int(assigned_to) < 1:
                raise ValidationError({"assigned_to": "Enter a positive integer."})
            queryset = queryset.filter(assigned_to_id=int(assigned_to))
        is_closed = self.request.query_params.get("is_closed")
        if is_closed is not None:
            if is_closed not in {"true", "false"}:
                raise ValidationError({"is_closed": "Must be true or false."})
            queryset = queryset.filter(closed_at__isnull=is_closed == "false")
        return queryset

    @extend_schema(parameters=[OpenApiParameter("status", str), OpenApiParameter("assigned_to", int), OpenApiParameter("is_closed", bool)])
    def list(self, request, *args, **kwargs): return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        if request.user.role not in ELEVATED:
            raise PermissionDenied("After-sales request creation is not allowed.")
        return super().create(request, *args, **kwargs)

    @extend_schema(responses={200: AfterSalesAssigneeSerializer(many=True), 403: ACCESS_DENIED_RESPONSE})
    @action(detail=False, methods=["get"])
    def assignees(self, request):
        if request.user.role not in ELEVATED:
            raise PermissionDenied("After-sales assignee list is not allowed.")
        serializer = AssignmentSerializer()
        queryset = serializer.fields["to_user"].queryset.order_by("username")
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response([{"id": user.pk, "display": user.get_full_name() or user.username} for user in page])

    @extend_schema(request=AssignmentSerializer, responses={200: AfterSalesRequestSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE})
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        serializer = AssignmentSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        item = assign_after_sales_request(actor=request.user, request=self.get_object(), **serializer.validated_data)
        return Response(self.get_serializer(item).data)

    @extend_schema(request=StatusTransitionSerializer, responses={200: AfterSalesRequestSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE})
    @action(detail=True, methods=["post"], url_path="transition-status")
    def transition_status(self, request, pk=None):
        serializer = StatusTransitionSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        item = transition_after_sales_status(actor=request.user, request=self.get_object(), **serializer.validated_data)
        return Response(self.get_serializer(item).data)

    @extend_schema(request=CloseSerializer, responses={200: AfterSalesRequestSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE})
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        serializer = CloseSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        item = close_after_sales_request(actor=request.user, request=self.get_object(), **serializer.validated_data)
        return Response(self.get_serializer(item).data)

    @extend_schema(responses={200: AfterSalesHistorySerializer(many=True), 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE})
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        item = self.get_object()
        queryset = item.history.select_related("actor", "from_user", "to_user")
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(AfterSalesHistorySerializer(page, many=True).data)
