from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema

from accounts.models import User
from common.viewsets import NoDestroyModelViewSet
from sales.models import Customer, CustomerPhone, Interaction, Lead, Product, Sale
from sales.selectors import customers_for, interactions_for, leads_for, phones_for, products_for, sales_for
from sales.serializers import CancelSaleSerializer, CustomerPhoneSerializer, CustomerSerializer, InteractionSerializer, LeadSerializer, ProductSerializer, ReassignSerializer, SaleSerializer
from sales.services import cancel_or_correct_sale, deactivate_customer, deactivate_product, reassign_lead


MANAGERS = {User.Role.SALES_MANAGER, User.Role.PLATFORM_ADMIN}


class CustomerViewSet(NoDestroyModelViewSet):
    queryset = Customer.objects.none()
    serializer_class = CustomerSerializer
    search_fields = ["full_name", "national_id", "email", "phones__normalized_phone"]
    ordering_fields = ["full_name", "created_at", "updated_at"]

    def get_queryset(self):
        return customers_for(self.request.user).select_related("created_by").prefetch_related("phones")

    @action(detail=True, methods=["post"])
    @extend_schema(
        request=None,
        responses={200: CustomerSerializer, 400: OpenApiResponse(description="Customer is already inactive."), 403: OpenApiResponse(description="Operational write is not allowed."), 404: OpenApiResponse(description="Customer is outside actor scope.")},
    )
    def deactivate(self, request, pk=None):
        customer = deactivate_customer(actor=request.user, customer=self.get_object())
        return Response(self.get_serializer(customer).data)


class CustomerPhoneViewSet(NoDestroyModelViewSet):
    queryset = CustomerPhone.objects.none()
    serializer_class = CustomerPhoneSerializer
    search_fields = ["raw_phone", "normalized_phone", "customer__full_name"]
    ordering_fields = ["created_at", "is_primary"]

    def get_queryset(self):
        return phones_for(self.request.user).select_related("customer")


class LeadViewSet(NoDestroyModelViewSet):
    queryset = Lead.objects.none()
    serializer_class = LeadSerializer
    search_fields = ["customer__full_name", "source", "campaign_or_batch", "notes"]
    ordering_fields = ["created_at", "next_follow_up_at", "assigned_at"]

    def get_queryset(self):
        queryset = leads_for(self.request.user).select_related("customer", "assigned_to", "assigned_by", "interested_product")
        status_value = self.request.query_params.get("status")
        if status_value is not None:
            queryset = queryset.filter(status=status_value)
        return queryset

    @extend_schema(parameters=[OpenApiParameter("status", str, description="Exact backend-owned lead status value.")])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @extend_schema(
        request=ReassignSerializer,
        responses={200: LeadSerializer, 400: OpenApiResponse(description="Target is invalid or assignment is unchanged."), 403: OpenApiResponse(description="Sales Manager or Platform Admin role is required."), 404: OpenApiResponse(description="Lead is outside actor scope.")},
        examples=[OpenApiExample("Lead reassignment", value={"to_user": 42, "reason": "workload balance"}, request_only=True)],
        description="Atomically reassigns a Lead and creates assignment history plus a safe audit record.",
    )
    def reassign(self, request, pk=None):
        serializer = ReassignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead = reassign_lead(actor=request.user, lead=self.get_object(), **serializer.validated_data)
        return Response(self.get_serializer(lead).data)


class InteractionViewSet(NoDestroyModelViewSet):
    queryset = Interaction.objects.none()
    serializer_class = InteractionSerializer
    http_method_names = ["get", "post", "head", "options"]
    search_fields = ["phone", "outcome", "notes", "lead__customer__full_name"]
    ordering_fields = ["occurred_at", "next_follow_up_at", "created_at"]

    def get_queryset(self):
        return interactions_for(self.request.user).select_related("lead", "customer", "agent")


class ProductViewSet(NoDestroyModelViewSet):
    queryset = Product.objects.none()
    serializer_class = ProductSerializer
    search_fields = ["sku", "name", "description"]
    ordering_fields = ["sku", "name", "current_price", "created_at"]

    def get_queryset(self):
        return products_for(self.request.user).select_related("created_by", "updated_by")

    def _require_manager(self):
        if self.request.user.role not in MANAGERS:
            raise PermissionDenied("Product management is not allowed.")

    def perform_create(self, serializer):
        self._require_manager()
        serializer.save()

    def perform_update(self, serializer):
        self._require_manager()
        serializer.save()

    @action(detail=True, methods=["post"])
    @extend_schema(
        request=None,
        responses={200: ProductSerializer, 400: OpenApiResponse(description="Product is already inactive."), 403: OpenApiResponse(description="Sales Manager or Platform Admin role is required."), 404: OpenApiResponse(description="Product does not exist.")},
    )
    def deactivate(self, request, pk=None):
        product = deactivate_product(actor=request.user, product=self.get_object())
        return Response(self.get_serializer(product).data)


class SaleViewSet(NoDestroyModelViewSet):
    queryset = Sale.objects.none()
    serializer_class = SaleSerializer
    http_method_names = ["get", "post", "head", "options"]
    search_fields = ["lead__customer__full_name", "product__name", "notes"]
    ordering_fields = ["sold_at", "total_amount", "created_at"]

    def get_queryset(self):
        queryset = sales_for(self.request.user).select_related("lead", "customer", "sold_by", "product")
        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset

    @extend_schema(parameters=[OpenApiParameter("status", str, enum=[Sale.Status.CONFIRMED, Sale.Status.CANCELLED])])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @extend_schema(
        request=CancelSaleSerializer,
        responses={200: SaleSerializer, 400: OpenApiResponse(description="Sale is already cancelled or request is invalid."), 403: OpenApiResponse(description="Sales Manager or Platform Admin role is required."), 404: OpenApiResponse(description="Sale is outside actor scope.")},
        examples=[OpenApiExample("Sale cancellation", value={"reason": "approved business correction"}, request_only=True)],
        description="Cancels a confirmed Sale. Raw reason text is not copied into the audit payload.",
    )
    def cancel(self, request, pk=None):
        serializer = CancelSaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sale = cancel_or_correct_sale(actor=request.user, sale=self.get_object(), operation="cancel", **serializer.validated_data)
        return Response(self.get_serializer(sale).data)
