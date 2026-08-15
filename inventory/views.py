from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.models import User
from common.openapi import (
    ACCESS_DENIED_RESPONSE,
    CONFLICT_RESPONSE,
    NOT_FOUND_RESPONSE,
    THROTTLED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from common.permissions import IsActiveAuthenticated
from common.throttles import SensitiveActionThrottleMixin
from common.viewsets import NoDestroyModelViewSet, StrictQueryParametersMixin
from inventory.models import StockItem, StockMovement, Warehouse
from inventory.permissions import HasInventoryCapability
from inventory.selectors import stock_items_for, stock_movements_for, warehouses_for
from inventory.serializers import (
    StockItemSerializer,
    StockMovementSerializer,
    StockTransferSerializer,
    WarehouseSerializer,
)
from inventory.services import deactivate_warehouse, reactivate_warehouse, transfer_stock
from rest_framework import mixins, viewsets


ELEVATED_OPERATORS = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}


class WarehouseViewSet(SensitiveActionThrottleMixin, NoDestroyModelViewSet):
    required_feature = "inventory"
    required_capabilities = ("inventory.read", "inventory.manage")
    permission_classes = [IsActiveAuthenticated, HasInventoryCapability]
    queryset = Warehouse.objects.none()
    serializer_class = WarehouseSerializer
    sensitive_actions = frozenset({"create", "update", "partial_update", "deactivate", "reactivate"})
    search_fields = ["code", "name", "address"]
    ordering_fields = ["name", "code", "created_at"]
    list_query_parameters = {"is_active"}

    def get_queryset(self):
        queryset = warehouses_for(self.request.user).select_related("created_by", "updated_by")
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            if is_active not in {"true", "false"}:
                raise ValidationError({"is_active": "Must be true or false."})
            queryset = queryset.filter(is_active=is_active == "true")
        return queryset

    @extend_schema(parameters=[OpenApiParameter("is_active", bool, description="Exact warehouse active state.")])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def _require_manager(self):
        if self.request.user.role not in ELEVATED_OPERATORS:
            raise PermissionDenied("Inventory management is not allowed.")

    def create(self, request, *args, **kwargs):
        self._require_manager()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._require_manager()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._require_manager()
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(
        request=None,
        responses={200: WarehouseSerializer, 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE},
    )
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        self._require_manager()
        warehouse = deactivate_warehouse(actor=request.user, warehouse=self.get_object())
        return Response(self.get_serializer(warehouse).data)

    @extend_schema(
        request=None,
        responses={200: WarehouseSerializer, 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE},
    )
    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        self._require_manager()
        warehouse = reactivate_warehouse(actor=request.user, warehouse=self.get_object())
        return Response(self.get_serializer(warehouse).data)


class StockItemViewSet(StrictQueryParametersMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    required_feature = "inventory"
    required_capabilities = ("inventory.read", "inventory.manage")
    permission_classes = [IsActiveAuthenticated, HasInventoryCapability]
    queryset = StockItem.objects.none()
    serializer_class = StockItemSerializer
    search_fields = ["product__name", "product__sku", "product__barcode", "warehouse__name"]
    ordering_fields = ["quantity", "average_cost", "last_movement_at"]
    list_query_parameters = {"warehouse", "product", "below_or_equal"}

    def _positive_int(self, name):
        value = self.request.query_params.get(name)
        if value is None:
            return None
        if not value.lstrip("-").isdecimal() or (name != "below_or_equal" and int(value) < 1):
            raise ValidationError({name: "Enter a valid integer."})
        return int(value)

    def get_queryset(self):
        queryset = stock_items_for(self.request.user).select_related("warehouse", "product")
        warehouse = self._positive_int("warehouse")
        if warehouse is not None:
            queryset = queryset.filter(warehouse_id=warehouse)
        product = self._positive_int("product")
        if product is not None:
            queryset = queryset.filter(product_id=product)
        threshold = self._positive_int("below_or_equal")
        if threshold is not None:
            queryset = queryset.filter(quantity__lte=threshold)
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("warehouse", int, description="Exact Warehouse ID."),
            OpenApiParameter("product", int, description="Exact Product ID."),
            OpenApiParameter("below_or_equal", int, description="Only levels at or below this quantity."),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class StockMovementViewSet(SensitiveActionThrottleMixin, StrictQueryParametersMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    required_feature = "inventory"
    required_capabilities = ("inventory.read", "inventory.manage")
    permission_classes = [IsActiveAuthenticated, HasInventoryCapability]
    queryset = StockMovement.objects.none()
    serializer_class = StockMovementSerializer
    sensitive_actions = frozenset({"create", "transfer"})
    search_fields = ["product__name", "product__sku", "reference_number", "notes"]
    ordering_fields = ["occurred_at", "quantity", "created_at"]
    list_query_parameters = {"warehouse", "product", "movement_type"}

    def get_queryset(self):
        queryset = stock_movements_for(self.request.user).select_related(
            "warehouse", "product", "created_by"
        )
        for parameter, field in (("warehouse", "warehouse_id"), ("product", "product_id")):
            value = self.request.query_params.get(parameter)
            if value is not None:
                if not value.isdecimal() or int(value) < 1:
                    raise ValidationError({parameter: "Enter a positive integer."})
                queryset = queryset.filter(**{field: int(value)})
        movement_type = self.request.query_params.get("movement_type")
        if movement_type is not None:
            if movement_type not in StockMovement.MovementType.values:
                raise ValidationError({"movement_type": "Unknown movement type."})
            queryset = queryset.filter(movement_type=movement_type)
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("warehouse", int, description="Exact Warehouse ID."),
            OpenApiParameter("product", int, description="Exact Product ID."),
            OpenApiParameter(
                "movement_type", str, enum=list(StockMovement.MovementType.values)
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        if request.user.role not in ELEVATED_OPERATORS:
            raise PermissionDenied("Inventory management is not allowed.")
        return super().create(request, *args, **kwargs)

    @extend_schema(
        request=StockTransferSerializer,
        responses={
            201: StockMovementSerializer(many=True),
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            409: CONFLICT_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description="Moves stock between two warehouses as one transactional pair of movements.",
    )
    @action(detail=False, methods=["post"])
    def transfer(self, request):
        if request.user.role not in ELEVATED_OPERATORS:
            raise PermissionDenied("Inventory management is not allowed.")
        serializer = StockTransferSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if data.get("occurred_at") is None:
            data.pop("occurred_at", None)
        outgoing, incoming = transfer_stock(actor=request.user, **data)
        payload = StockMovementSerializer(
            [outgoing, incoming], many=True, context=self.get_serializer_context()
        ).data
        return Response(payload, status=201)
