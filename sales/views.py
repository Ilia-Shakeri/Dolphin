from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema

from accounts.access import crm_identities
from accounts.models import User
from common.openapi import (
    ACCESS_DENIED_RESPONSE,
    CONFLICT_RESPONSE,
    NOT_FOUND_RESPONSE,
    THROTTLED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from common.throttles import SensitiveActionThrottleMixin
from common.viewsets import NoDestroyModelViewSet
from sales.models import Customer, CustomerPhone, Interaction, Lead, Product, Sale, SalesDocument
from sales.selectors import customers_for, interactions_for, lead_work_queue_for, leads_for, phones_for, products_for, sales_documents_for, sales_for
from sales.serializers import CancelSaleSerializer, CustomerPhoneSerializer, CustomerSerializer, InteractionSerializer, LeadAssigneeSerializer, LeadAssignmentHistorySerializer, LeadSerializer, PostalStatusHistorySerializer, PostalStatusTransitionSerializer, ProductSerializer, ReassignSerializer, SaleSerializer, SalesDocumentSerializer
from sales.services import cancel_or_correct_sale, deactivate_customer, deactivate_customer_phone, deactivate_product, deactivate_sales_document, reassign_lead, transition_postal_status


ELEVATED_OPERATORS = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}


class CustomerViewSet(SensitiveActionThrottleMixin, NoDestroyModelViewSet):
    queryset = Customer.objects.none()
    serializer_class = CustomerSerializer
    sensitive_actions = frozenset({"deactivate"})
    search_fields = [
        "full_name",
        "national_id",
        "email",
        "province",
        "city",
        "postal_code",
        "category",
        "address",
        "phones__normalized_phone",
    ]
    ordering_fields = ["full_name", "created_at", "updated_at"]
    action_query_parameters = {
        "leads": {"page"},
        "interactions": {"page"},
        "sales": {"page"},
    }

    def get_queryset(self):
        return customers_for(self.request.user).select_related("created_by").prefetch_related("phones")

    @extend_schema(
        request=None,
        responses={
            200: CustomerSerializer,
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            409: CONFLICT_RESPONSE,
        },
    )
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        customer = deactivate_customer(actor=request.user, customer=self.get_object())
        return Response(self.get_serializer(customer).data)

    @extend_schema(
        parameters=[OpenApiParameter("page", int, description="Related Lead result page.")],
        responses={200: LeadSerializer(many=True), 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE},
    )
    @action(detail=True, methods=["get"])
    def leads(self, request, pk=None):
        customer = self.get_object()
        queryset = leads_for(request.user).filter(customer=customer).select_related(
            "customer", "assigned_to", "assigned_by", "interested_product"
        )
        page = self.paginate_queryset(queryset)
        serializer = LeadSerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        parameters=[OpenApiParameter("page", int, description="Related Interaction result page.")],
        responses={200: InteractionSerializer(many=True), 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE},
    )
    @action(detail=True, methods=["get"])
    def interactions(self, request, pk=None):
        customer = self.get_object()
        queryset = interactions_for(request.user).filter(customer=customer).select_related(
            "lead", "customer", "agent"
        )
        page = self.paginate_queryset(queryset)
        serializer = InteractionSerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        parameters=[OpenApiParameter("page", int, description="Related Sale result page.")],
        responses={200: SaleSerializer(many=True), 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE},
    )
    @action(detail=True, methods=["get"])
    def sales(self, request, pk=None):
        customer = self.get_object()
        queryset = sales_for(request.user).filter(customer=customer).select_related(
            "lead", "customer", "sold_by", "product"
        )
        page = self.paginate_queryset(queryset)
        serializer = SaleSerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)


class CustomerPhoneViewSet(SensitiveActionThrottleMixin, NoDestroyModelViewSet):
    queryset = CustomerPhone.objects.none()
    serializer_class = CustomerPhoneSerializer
    search_fields = ["raw_phone", "normalized_phone", "customer__full_name"]
    ordering_fields = ["created_at", "is_primary"]
    list_query_parameters = {"customer"}
    sensitive_actions = frozenset({"deactivate"})

    def get_queryset(self):
        queryset = phones_for(self.request.user).select_related("customer")
        customer_id = self.request.query_params.get("customer")
        if customer_id is not None:
            if not customer_id.isdecimal() or int(customer_id) < 1:
                raise ValidationError({"customer": "Enter a positive integer."})
            queryset = queryset.filter(customer_id=int(customer_id))
        return queryset

    @extend_schema(parameters=[OpenApiParameter("customer", int, description="Exact positive Customer ID inside actor scope.")])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=None,
        responses={
            200: CustomerPhoneSerializer,
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            409: CONFLICT_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
    )
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        phone = deactivate_customer_phone(actor=request.user, phone=self.get_object())
        return Response(self.get_serializer(phone).data)


class LeadViewSet(SensitiveActionThrottleMixin, NoDestroyModelViewSet):
    queryset = Lead.objects.none()
    serializer_class = LeadSerializer
    sensitive_actions = frozenset({"reassign"})
    search_fields = ["customer__full_name", "source", "campaign_or_batch", "notes"]
    ordering_fields = ["created_at", "next_follow_up_at", "assigned_at"]
    list_query_parameters = {"status"}
    action_query_parameters = {
        "assignees": {"page"},
        "assignment_history": {"page"},
        "work_queue": {"page"},
    }

    def get_queryset(self):
        queryset = leads_for(self.request.user).select_related("customer", "assigned_to", "assigned_by", "interested_product")
        status_value = self.request.query_params.get("status")
        if status_value is not None:
            queryset = queryset.filter(status=status_value)
        return queryset

    @extend_schema(parameters=[OpenApiParameter("status", str, description="Exact backend-owned lead status value.")])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        responses={200: LeadSerializer(many=True), 403: ACCESS_DENIED_RESPONSE},
        description="Returns the authenticated Sales Agent's assigned Leads, with dated follow-ups first.",
    )
    @action(detail=False, methods=["get"], url_path="work-queue")
    def work_queue(self, request):
        if request.user.role != User.Role.SALES_AGENT:
            raise PermissionDenied("The work queue is available only to Sales Agents.")
        queryset = lead_work_queue_for(request.user).select_related(
            "customer", "assigned_to", "assigned_by", "interested_product"
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(responses={200: LeadAssigneeSerializer(many=True), 403: ACCESS_DENIED_RESPONSE})
    @action(detail=False, methods=["get"])
    def assignees(self, request):
        if request.user.role not in ELEVATED_OPERATORS:
            raise PermissionDenied("Lead reassignment is not allowed.")
        queryset = crm_identities(
            User.objects.filter(role=User.Role.SALES_AGENT, is_active=True)
        ).order_by("username")
        page = self.paginate_queryset(queryset)
        serializer = LeadAssigneeSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        responses={
            200: LeadAssignmentHistorySerializer(many=True),
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
        }
    )
    @action(detail=True, methods=["get"], url_path="assignment-history")
    def assignment_history(self, request, pk=None):
        lead = self.get_object()
        queryset = lead.assignment_history.select_related(
            "from_user", "to_user", "changed_by"
        ).all()
        page = self.paginate_queryset(queryset)
        serializer = LeadAssignmentHistorySerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        request=ReassignSerializer,
        responses={
            200: LeadSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            409: CONFLICT_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        examples=[OpenApiExample("Lead reassignment", value={"to_user": 42, "reason": "workload balance"}, request_only=True)],
        description="Atomically reassigns a Lead and creates assignment history plus a safe audit record.",
    )
    @action(detail=True, methods=["post"])
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


class ProductViewSet(SensitiveActionThrottleMixin, NoDestroyModelViewSet):
    queryset = Product.objects.none()
    serializer_class = ProductSerializer
    sensitive_actions = frozenset({"create", "update", "partial_update", "deactivate"})
    search_fields = ["sku", "name", "description"]
    ordering_fields = ["sku", "name", "current_price", "created_at"]
    list_query_parameters = {"is_active"}

    def get_queryset(self):
        queryset = products_for(self.request.user).select_related("created_by", "updated_by")
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            if is_active not in {"true", "false"}:
                raise ValidationError({"is_active": "Must be true or false."})
            queryset = queryset.filter(is_active=is_active == "true")
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "is_active",
                bool,
                description="Filter by the existing Product active state.",
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def _require_manager(self):
        if self.request.user.role not in ELEVATED_OPERATORS:
            raise PermissionDenied("Product management is not allowed.")

    def perform_create(self, serializer):
        self._require_manager()
        serializer.save()

    def perform_update(self, serializer):
        self._require_manager()
        serializer.save()

    @extend_schema(
        request=None,
        responses={
            200: ProductSerializer,
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            409: CONFLICT_RESPONSE,
        },
    )
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        product = deactivate_product(actor=request.user, product=self.get_object())
        return Response(self.get_serializer(product).data)


class SaleViewSet(SensitiveActionThrottleMixin, NoDestroyModelViewSet):
    queryset = Sale.objects.none()
    serializer_class = SaleSerializer
    sensitive_actions = frozenset({"create", "cancel"})
    http_method_names = ["get", "post", "head", "options"]
    search_fields = ["lead__customer__full_name", "product__name", "notes"]
    ordering_fields = ["sold_at", "total_amount", "created_at"]
    list_query_parameters = {"status"}

    def get_queryset(self):
        queryset = sales_for(self.request.user).select_related("lead", "customer", "sold_by", "product")
        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset

    @extend_schema(parameters=[OpenApiParameter("status", str, enum=[Sale.Status.CONFIRMED, Sale.Status.CANCELLED])])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=CancelSaleSerializer,
        responses={
            200: SaleSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            409: CONFLICT_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        examples=[OpenApiExample("Sale cancellation", value={"reason": "approved business correction"}, request_only=True)],
        description="Cancels a confirmed Sale. Raw reason text is not copied into the audit payload.",
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        serializer = CancelSaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sale = cancel_or_correct_sale(actor=request.user, sale=self.get_object(), operation="cancel", **serializer.validated_data)
        return Response(self.get_serializer(sale).data)


class SalesDocumentViewSet(SensitiveActionThrottleMixin, NoDestroyModelViewSet):
    queryset = SalesDocument.objects.none()
    serializer_class = SalesDocumentSerializer
    sensitive_actions = frozenset({"create", "transition_postal_status", "deactivate"})
    http_method_names = ["get", "post", "head", "options"]
    search_fields = ["document_number", "customer__full_name", "province_snapshot", "city_snapshot", "postal_code_snapshot", "address_snapshot", "postal_status"]
    ordering_fields = ["registered_at", "document_number", "province_snapshot", "city_snapshot", "postal_status"]
    list_query_parameters = {"postal_status", "province", "city", "is_active"}
    action_query_parameters = {"postal_history": {"page"}}

    def get_queryset(self):
        queryset = sales_documents_for(self.request.user).select_related("customer", "sale", "registered_by")
        filters = {
            "postal_status": "postal_status",
            "province": "province_snapshot",
            "city": "city_snapshot",
        }
        for parameter, field in filters.items():
            value = self.request.query_params.get(parameter)
            if value is not None:
                queryset = queryset.filter(**{field: value})
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            if is_active not in {"true", "false"}:
                raise ValidationError({"is_active": "Must be true or false."})
            queryset = queryset.filter(is_active=is_active == "true")
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("postal_status", str, description="Exact current postal status."),
            OpenApiParameter("province", str, description="Exact snapshotted province."),
            OpenApiParameter("city", str, description="Exact snapshotted city."),
            OpenApiParameter("is_active", bool, description="Exact active state."),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        if request.user.role not in ELEVATED_OPERATORS:
            raise PermissionDenied("Sales document registration is not allowed.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        if self.request.user.role not in ELEVATED_OPERATORS:
            raise PermissionDenied("Sales document registration is not allowed.")
        serializer.save()

    @extend_schema(request=PostalStatusTransitionSerializer, responses={200: SalesDocumentSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE})
    @action(detail=True, methods=["post"], url_path="transition-postal-status")
    def transition_postal_status(self, request, pk=None):
        serializer = PostalStatusTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = transition_postal_status(actor=request.user, document=self.get_object(), **serializer.validated_data)
        return Response(self.get_serializer(document).data)

    @extend_schema(responses={200: PostalStatusHistorySerializer(many=True), 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE})
    @action(detail=True, methods=["get"], url_path="postal-history")
    def postal_history(self, request, pk=None):
        document = self.get_object()
        queryset = document.postal_history.select_related("changed_by").all()
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(PostalStatusHistorySerializer(page, many=True).data)

    @extend_schema(request=None, responses={200: SalesDocumentSerializer, 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE})
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        document = deactivate_sales_document(actor=request.user, document=self.get_object())
        return Response(self.get_serializer(document).data)
