from datetime import datetime, time, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema

from accounts.access import crm_identities, has_any_capability
from accounts.models import User
from common.openapi import (
    ACCESS_DENIED_RESPONSE,
    CONFLICT_RESPONSE,
    NOT_FOUND_RESPONSE,
    THROTTLED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from common.throttles import SensitiveActionThrottleMixin
from common.permissions import IsActiveAuthenticated
from common.viewsets import AdminHardDeleteModelViewSet
from sales.permissions import HasSalesCapability
from sales.models import Customer, CustomerPhone, Interaction, Lead, Product, ProductCategory, Sale, SalesDocument, TargetAudienceMember
from sales.selectors import customers_for, interactions_for, target_audience_for, lead_work_queue_for, leads_for, phones_for, product_categories_for, products_for, sales_documents_for, sales_for
from sales.customer_imports import import_customers_from_workbook
from sales.imports import import_products_from_workbook
from sales.serializers import CancelSaleSerializer, CustomerActivationSerializer, CustomerImportResultSerializer, ProductActivationSerializer, ProductImportResultSerializer, CustomerPhoneSerializer, CustomerSerializer, InteractionSerializer, LeadAssigneeSerializer, LeadAssignmentHistorySerializer, LeadSerializer, PostalStatusHistorySerializer, PostalStatusTransitionSerializer, ProductCategorySerializer, ProductSerializer, ReassignSerializer, SaleSerializer, SalesDocumentSerializer, TargetAudienceMemberSerializer
from sales.services import cancel_or_correct_sale, deactivate_customer, set_customer_active, deactivate_customer_phone, deactivate_product, set_product_active, deactivate_product_category, deactivate_sales_document, reactivate_product_category, reassign_lead, transition_postal_status


ELEVATED_OPERATORS = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}


def _start_of_day(day):
    """Midnight on `day` in the deployment's timezone.

    Built in local time on purpose: a person filtering "from 1405/05/01" means
    the day as it is lived in Tehran, not a UTC boundary that would cut it three
    and a half hours early.
    """
    return timezone.make_aware(datetime.combine(day, time.min))


class CustomerViewSet(SensitiveActionThrottleMixin, AdminHardDeleteModelViewSet):
    required_feature = "customers"
    required_capabilities = ("customers.scoped", "customers.company")
    required_write_capabilities = ("customers.manage",)
    permission_classes = [IsActiveAuthenticated, HasSalesCapability]
    queryset = Customer.objects.none()
    serializer_class = CustomerSerializer
    sensitive_actions = frozenset({"deactivate", "import_xlsx"})
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
    #: A registration-date window (both bounds optional and inclusive of the
    #: whole day they name, which is what a person means by "from x to y"), and
    #: which customer book to read.
    list_query_parameters = {"created_from", "created_to", "kind"}
    action_query_parameters = {
        "leads": {"page"},
        "interactions": {"page"},
        "sales": {"page"},
    }

    def get_queryset(self):
        queryset = (
            customers_for(self.request.user).select_related("created_by").prefetch_related("phones")
        )
        # Narrowing only. `customers_for` has already decided which books this
        # caller may read at all, so a marketer asking for `kind=legal` gets an
        # empty page rather than someone else's customers.
        kind = self.request.query_params.get("kind")
        if kind is not None:
            if kind not in Customer.Kind.values:
                raise ValidationError({"kind": "نوع مشتری را از فهرست انتخاب کنید."})
            queryset = queryset.filter(kind=kind)
        return self._filter_by_registration_date(queryset)

    def _filter_by_registration_date(self, queryset):
        """Narrow to a registration-date window given as two ISO dates.

        The upper bound is exclusive of the next day rather than inclusive of a
        timestamp, so a customer registered at 23:59 on the closing day is still
        inside the window. A malformed date is a request error, not a silently
        ignored parameter — quietly dropping it would show the wrong rows and
        look like the filter worked.
        """
        bounds = {
            "created_from": self.request.query_params.get("created_from"),
            "created_to": self.request.query_params.get("created_to"),
        }
        parsed = {}
        errors = {}
        for name, raw in bounds.items():
            if not raw:
                continue
            value = parse_date(raw)
            if value is None:
                errors[name] = ["تاریخ را به قالب YYYY-MM-DD وارد کنید."]
            else:
                parsed[name] = value
        if errors:
            raise ValidationError(errors)
        if "created_from" in parsed:
            queryset = queryset.filter(created_at__gte=_start_of_day(parsed["created_from"]))
        if "created_to" in parsed:
            queryset = queryset.filter(
                created_at__lt=_start_of_day(parsed["created_to"] + timedelta(days=1))
            )
        return queryset

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "binary"},
                    "kind": {"type": "string", "enum": ["individual", "legal"]},
                },
            }
        },
        responses={
            200: CustomerImportResultSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
        },
        description=(
            "Create customers in bulk from a filled export of "
            "GET /api/v1/exports/customers.xlsx. Columns are matched by header name. "
            "`kind` names the list to import into and overrides the file's own kind "
            "column. A row whose phone or national ID already exists is skipped and "
            "counted as a duplicate — an import never overwrites an existing customer."
        ),
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="import-xlsx",
        parser_classes=[MultiPartParser],
    )
    def import_xlsx(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "فایل تکمیل‌شده را پیوست کنید."})
        if not upload.name.lower().endswith(".xlsx"):
            raise ValidationError({"file": "فقط فایل با پسوند xlsx. پذیرفته می‌شود."})
        result = import_customers_from_workbook(
            actor=request.user,
            stream=upload,
            kind=request.data.get("kind", Customer.Kind.INDIVIDUAL),
        )
        return Response(CustomerImportResultSerializer(result).data)

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
        request=CustomerActivationSerializer,
        responses={
            200: CustomerSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            409: CONFLICT_RESPONSE,
        },
        description=(
            "Turn a customer active or inactive. Platform Admin only. Deactivating hides the "
            "customer from day-to-day work and removes nothing: orders, invoices, payments and "
            "ledger entries all survive, which is why it is reversible."
        ),
    )
    @action(detail=True, methods=["post"], url_path="set-active")
    def set_active(self, request, pk=None):
        serializer = CustomerActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = set_customer_active(
            actor=request.user,
            customer=self.get_object(),
            is_active=serializer.validated_data["is_active"],
        )
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


class CustomerPhoneViewSet(SensitiveActionThrottleMixin, AdminHardDeleteModelViewSet):
    required_feature = "customers"
    required_capabilities = ("customers.scoped", "customers.company")
    required_write_capabilities = ("customers.manage",)
    permission_classes = [IsActiveAuthenticated, HasSalesCapability]
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
                raise ValidationError({"customer": "یک عدد صحیح مثبت وارد کنید."})
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


class LeadViewSet(SensitiveActionThrottleMixin, AdminHardDeleteModelViewSet):
    required_feature = "leads"
    required_capabilities = ("leads.scoped", "leads.company")
    required_write_capabilities = ("leads.manage",)
    permission_classes = [IsActiveAuthenticated, HasSalesCapability]
    queryset = Lead.objects.none()
    serializer_class = LeadSerializer
    sensitive_actions = frozenset({"reassign"})
    search_fields = ["customer__full_name", "source", "campaign_or_batch", "notes"]
    ordering_fields = ["created_at", "next_follow_up_at", "assigned_at"]
    #: `follow_up_from`/`follow_up_to` are the follow-up calendar's own window —
    #: both bounds are exact ISO instants, because the calendar grid already
    #: knows precisely where each visible cell starts and ends, unlike a plain
    #: registration-date filter where a person types a bare day.
    list_query_parameters = {"status", "follow_up_from", "follow_up_to"}
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
        return self._filter_by_follow_up(queryset)

    def _filter_by_follow_up(self, queryset):
        """Narrow to a `next_follow_up_at` window — the follow-up calendar's own filter.

        A lead with no follow-up date set is excluded by the bound comparison
        itself, which is exactly what a calendar wants: nothing to draw for it.
        """
        bounds = {
            "follow_up_from": self.request.query_params.get("follow_up_from"),
            "follow_up_to": self.request.query_params.get("follow_up_to"),
        }
        parsed = {}
        errors = {}
        for name, raw in bounds.items():
            if not raw:
                continue
            value = parse_datetime(raw)
            if value is None or timezone.is_naive(value):
                errors[name] = ["زمان را در قالب ISO 8601 همراه با منطقه زمانی وارد کنید."]
            else:
                parsed[name] = value
        if errors:
            raise ValidationError(errors)
        if "follow_up_from" in parsed:
            queryset = queryset.filter(next_follow_up_at__gte=parsed["follow_up_from"])
        if "follow_up_to" in parsed:
            queryset = queryset.filter(next_follow_up_at__lt=parsed["follow_up_to"])
        return queryset

    @extend_schema(parameters=[
        OpenApiParameter("status", str, description="Exact backend-owned lead status value."),
        OpenApiParameter("follow_up_from", str, description="Inclusive ISO 8601 instant; narrows to next_follow_up_at."),
        OpenApiParameter("follow_up_to", str, description="Exclusive ISO 8601 instant; narrows to next_follow_up_at."),
    ])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        responses={200: LeadSerializer(many=True), 403: ACCESS_DENIED_RESPONSE},
        description="Returns the authenticated Sales Agent's assigned Leads, with dated follow-ups first.",
    )
    @action(detail=False, methods=["get"], url_path="work-queue")
    def work_queue(self, request):
        if request.user.role != User.Role.SALES_AGENT:
            raise PermissionDenied("صف کاری فقط برای بازاریاب‌ها در دسترس است.")
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
            raise PermissionDenied("واگذاری مجدد سرنخ مجاز نیست.")
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


class InteractionViewSet(AdminHardDeleteModelViewSet):
    required_feature = "leads"
    required_capabilities = ("interactions.scoped", "interactions.company")
    required_write_capabilities = ("interactions.manage",)
    permission_classes = [IsActiveAuthenticated, HasSalesCapability]
    queryset = Interaction.objects.none()
    serializer_class = InteractionSerializer
    http_method_names = ["get", "post", "head", "options"]
    search_fields = ["phone", "outcome", "notes", "lead__customer__full_name"]
    ordering_fields = ["occurred_at", "next_follow_up_at", "created_at"]

    def get_queryset(self):
        return interactions_for(self.request.user).select_related("lead", "customer", "agent")


class TargetAudienceMemberViewSet(SensitiveActionThrottleMixin, AdminHardDeleteModelViewSet):
    """The campaign target audience ("جامعه هدف").

    Read scope follows the lead, so a marketer sees the audience of campaigns
    assigned to them. Write is refused for them in the service, which is where
    the boundary belongs — the read-only rendering in the template is a
    courtesy, not the control.
    """

    required_feature = "leads"
    required_capabilities = ("leads.scoped", "leads.company")
    required_write_capabilities = ("leads.manage",)
    permission_classes = [IsActiveAuthenticated, HasSalesCapability]
    queryset = TargetAudienceMember.objects.none()
    serializer_class = TargetAudienceMemberSerializer
    sensitive_actions = frozenset({"create", "update", "partial_update"})
    search_fields = ["full_name", "normalized_phone", "raw_phone"]
    ordering_fields = ["full_name", "status", "created_at"]
    list_query_parameters = {"lead", "status"}

    def get_queryset(self):
        queryset = target_audience_for(self.request.user).select_related("lead", "customer")
        lead = self.request.query_params.get("lead")
        if lead:
            queryset = queryset.filter(lead_id=lead)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset


class ProductCategoryViewSet(SensitiveActionThrottleMixin, AdminHardDeleteModelViewSet):
    required_feature = "products"
    required_capabilities = ("product_categories.read", "product_categories.manage")
    required_write_capabilities = ("product_categories.manage",)
    permission_classes = [IsActiveAuthenticated, HasSalesCapability]
    queryset = ProductCategory.objects.none()
    serializer_class = ProductCategorySerializer
    sensitive_actions = frozenset({"create", "update", "partial_update", "deactivate", "reactivate"})
    search_fields = ["code", "name", "description"]
    ordering_fields = ["display_order", "name", "code", "created_at"]
    list_query_parameters = {"is_active"}

    def get_queryset(self):
        queryset = product_categories_for(self.request.user).select_related("created_by", "updated_by")
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            if is_active not in {"true", "false"}:
                raise ValidationError({"is_active": "مقدار باید true یا false باشد."})
            queryset = queryset.filter(is_active=is_active == "true")
        return queryset

    @extend_schema(parameters=[OpenApiParameter("is_active", bool, description="Exact Category active state.")])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def _require_manager(self):
        if not has_any_capability(self.request.user, "product_categories.manage"):
            raise PermissionDenied("مدیریت دسته‌بندی کالا مجاز نیست.")

    def create(self, request, *args, **kwargs):
        self._require_manager()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._require_manager()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._require_manager()
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(request=None, responses={200: ProductCategorySerializer, 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE})
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        self._require_manager()
        category = deactivate_product_category(actor=request.user, category=self.get_object())
        return Response(self.get_serializer(category).data)

    @extend_schema(request=None, responses={200: ProductCategorySerializer, 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE, 409: CONFLICT_RESPONSE})
    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        self._require_manager()
        category = reactivate_product_category(actor=request.user, category=self.get_object())
        return Response(self.get_serializer(category).data)


class ProductViewSet(SensitiveActionThrottleMixin, AdminHardDeleteModelViewSet):
    required_feature = "products"
    required_capabilities = ("products.read", "products.manage")
    required_write_capabilities = ("products.manage",)
    permission_classes = [IsActiveAuthenticated, HasSalesCapability]
    queryset = Product.objects.none()
    serializer_class = ProductSerializer
    sensitive_actions = frozenset({"create", "update", "partial_update", "deactivate", "import_xlsx"})
    search_fields = ["sku", "name", "brand", "barcode", "category__name", "description"]
    ordering_fields = ["sku", "name", "brand", "current_price", "created_at"]
    list_query_parameters = {"is_active", "category"}

    def get_queryset(self):
        queryset = products_for(self.request.user).select_related("category", "created_by", "updated_by")
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            if is_active not in {"true", "false"}:
                raise ValidationError({"is_active": "مقدار باید true یا false باشد."})
            queryset = queryset.filter(is_active=is_active == "true")
        category = self.request.query_params.get("category")
        if category is not None:
            try:
                category_id = int(category)
            except (TypeError, ValueError) as exc:
                raise ValidationError({"category": "باید عددی صحیح و مثبت باشد."}) from exc
            if category_id < 1 or str(category_id) != category:
                raise ValidationError({"category": "باید عددی صحیح و مثبت باشد."})
            queryset = queryset.filter(category_id=category_id)
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "is_active",
                bool,
                description="Filter by the existing Product active state.",
            ),
            OpenApiParameter("category", int, description="Exact Category ID after Product scope."),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def _require_manager(self):
        if not has_any_capability(self.request.user, "products.manage"):
            raise PermissionDenied("مدیریت کالا مجاز نیست.")

    def create(self, request, *args, **kwargs):
        self._require_manager()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._require_manager()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._require_manager()
        return super().partial_update(request, *args, **kwargs)

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

    @extend_schema(
        request={"multipart/form-data": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}},
        responses={
            200: ProductImportResultSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
        },
        description=(
            "Create products in bulk from a filled export of GET /api/v1/exports/products.xlsx. "
            "Columns are matched by header name. A row whose SKU already exists is skipped and "
            "counted as a duplicate — an import never overwrites an existing product. The "
            "response reports how many rows were created, skipped and rejected."
        ),
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="import-xlsx",
        parser_classes=[MultiPartParser],
    )
    def import_xlsx(self, request):
        # The viewset admits anyone holding read *or* manage, and `create_product`
        # refuses a reader on the first row it tries. Checked here as well so a
        # caller who cannot create products is refused before their file is
        # parsed at all — and so a file with no valid rows cannot answer 200 to
        # someone who was never allowed to import.
        if not has_any_capability(request.user, "products.manage"):
            raise PermissionDenied("مدیریت کالا مجاز نیست.")
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "فایل تکمیل‌شده را پیوست کنید."})
        if not upload.name.lower().endswith(".xlsx"):
            raise ValidationError({"file": "فقط فایل با پسوند xlsx. پذیرفته می‌شود."})
        result = import_products_from_workbook(actor=request.user, stream=upload)
        return Response(ProductImportResultSerializer(result).data)

    @extend_schema(
        request=ProductActivationSerializer,
        responses={
            200: ProductSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            409: CONFLICT_RESPONSE,
        },
        description=(
            "Turn a product active or inactive. Platform Admin only. An inactive product cannot "
            "be put on a new document; every existing line keeps its snapshot, so this removes "
            "nothing and can be undone."
        ),
    )
    @action(detail=True, methods=["post"], url_path="set-active")
    def set_active(self, request, pk=None):
        serializer = ProductActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = set_product_active(
            actor=request.user,
            product=self.get_object(),
            is_active=serializer.validated_data["is_active"],
        )
        return Response(self.get_serializer(product).data)


class SaleViewSet(SensitiveActionThrottleMixin, AdminHardDeleteModelViewSet):
    required_feature = "sales"
    required_capabilities = ("sales.own", "sales.company")
    required_write_capabilities = ("sales.manage",)
    permission_classes = [IsActiveAuthenticated, HasSalesCapability]
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


class SalesDocumentViewSet(SensitiveActionThrottleMixin, AdminHardDeleteModelViewSet):
    required_feature = "sales_documents"
    required_capabilities = ("sales_documents.scoped", "sales_documents.company")
    required_write_capabilities = ("sales_documents.manage",)
    permission_classes = [IsActiveAuthenticated, HasSalesCapability]
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
                raise ValidationError({"is_active": "مقدار باید true یا false باشد."})
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
        if not has_any_capability(request.user, "sales_documents.manage"):
            raise PermissionDenied("ثبت سند فروش مجاز نیست.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        if not has_any_capability(self.request.user, "sales_documents.manage"):
            raise PermissionDenied("ثبت سند فروش مجاز نیست.")
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
