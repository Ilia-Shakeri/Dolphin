from django.db.models import F
from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.models import User
from billing.ledger import current_balance
from billing.models import (
    Cheque,
    CustomerLedgerEntry,
    Installment,
    InstallmentPlan,
    Invoice,
    Order,
    Payment,
    PaymentAllocation,
    Quotation,
)
from billing.payments import (
    allocate_payment,
    cancel_installment_plan,
    cancel_payment,
    create_installment_plan,
    record_opening_balance,
    release_allocation,
    transition_cheque,
)
from billing.permissions import HasBillingCapability
from billing.selectors import (
    cheques_for,
    installment_plans_for,
    installments_for,
    invoices_for,
    ledger_entries_for,
    orders_for,
    payments_for,
    quotations_for,
)
from billing.serializers import (
    AllocatePaymentSerializer,
    ChequeSerializer,
    ChequeStatusHistorySerializer,
    ChequeTransitionSerializer,
    ConvertOrderSerializer,
    CreateInstallmentPlanSerializer,
    CustomerLedgerEntrySerializer,
    DocumentItemsSerializer,
    InstallmentPlanSerializer,
    InstallmentSerializer,
    InvoiceSerializer,
    OpeningBalanceSerializer,
    OrderSerializer,
    PaymentAllocationSerializer,
    PaymentSerializer,
    QuotationSerializer,
    ReasonSerializer,
    DocumentStatusTransitionSerializer,
)
from billing.services import (
    cancel_invoice,
    convert_order_to_invoice,
    convert_quotation_to_order,
    issue_invoice,
    replace_invoice_items,
    replace_order_items,
    replace_quotation_items,
    transition_order,
    transition_quotation,
)
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
from sales.selectors import customers_for


ELEVATED_OPERATORS = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}


def _parse_date(value, field):
    parsed = parse_date(value)
    if parsed is None:
        raise ValidationError({field: "Enter a valid ISO date."})
    return parsed


WRITE_RESPONSES = {
    400: VALIDATION_ERROR_RESPONSE,
    403: ACCESS_DENIED_RESPONSE,
    404: NOT_FOUND_RESPONSE,
    409: CONFLICT_RESPONSE,
    429: THROTTLED_RESPONSE,
}


class CommercialDocumentViewSet(SensitiveActionThrottleMixin, NoDestroyModelViewSet):
    """Shared list/filter/items behaviour of Quotation, Order, and Invoice."""

    permission_classes = [IsActiveAuthenticated, HasBillingCapability]
    status_enum = None
    list_query_parameters = {"status", "customer"}

    def filtered(self, queryset):
        status_value = self.request.query_params.get("status")
        if status_value is not None:
            if status_value not in self.status_enum.values:
                raise ValidationError({"status": "Unknown status."})
            queryset = queryset.filter(status=status_value)
        customer = self.request.query_params.get("customer")
        if customer is not None:
            if not customer.isdecimal() or int(customer) < 1:
                raise ValidationError({"customer": "Enter a positive integer."})
            queryset = queryset.filter(customer_id=int(customer))
        return queryset

    def _require_manager(self, message):
        if self.request.user.role not in ELEVATED_OPERATORS:
            raise PermissionDenied(message)


class QuotationViewSet(CommercialDocumentViewSet):
    required_feature = "quotations"
    required_capabilities = ("quotations.scoped", "quotations.company")
    queryset = Quotation.objects.none()
    serializer_class = QuotationSerializer
    status_enum = Quotation.Status
    sensitive_actions = frozenset({"create", "update", "partial_update", "items", "transition", "convert"})
    search_fields = ["number", "customer__full_name", "notes", "items__product_name_snapshot"]
    ordering_fields = ["created_at", "total_amount", "valid_until", "number"]

    def get_queryset(self):
        return self.filtered(
            quotations_for(self.request.user)
            .select_related("customer", "lead", "created_by")
            .prefetch_related("items")
        )

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, enum=list(Quotation.Status.values)),
            OpenApiParameter("customer", int, description="Exact Customer ID inside actor scope."),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=DocumentItemsSerializer, responses={200: QuotationSerializer, **WRITE_RESPONSES})
    @action(detail=True, methods=["post"])
    def items(self, request, pk=None):
        serializer = DocumentItemsSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        document = replace_quotation_items(
            actor=request.user, quotation=self.get_object(), items=serializer.validated_data["items"]
        )
        return Response(self.get_serializer(document).data)

    @extend_schema(request=DocumentStatusTransitionSerializer, responses={200: QuotationSerializer, **WRITE_RESPONSES})
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        serializer = DocumentStatusTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = transition_quotation(
            actor=request.user, quotation=self.get_object(), **serializer.validated_data
        )
        return Response(self.get_serializer(document).data)

    @extend_schema(
        request=None,
        responses={201: OrderSerializer, **WRITE_RESPONSES},
        description="Copies an accepted quotation into a new draft order. The quotation is unchanged.",
    )
    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        order = convert_quotation_to_order(actor=request.user, quotation=self.get_object())
        return Response(
            OrderSerializer(order, context=self.get_serializer_context()).data, status=201
        )


class OrderViewSet(CommercialDocumentViewSet):
    required_feature = "orders"
    required_capabilities = ("orders.scoped", "orders.company")
    queryset = Order.objects.none()
    serializer_class = OrderSerializer
    status_enum = Order.Status
    sensitive_actions = frozenset({"create", "update", "partial_update", "items", "transition", "convert"})
    search_fields = ["number", "customer__full_name", "notes", "items__product_name_snapshot"]
    ordering_fields = ["created_at", "total_amount", "confirmed_at", "number"]

    def get_queryset(self):
        return self.filtered(
            orders_for(self.request.user)
            .select_related("customer", "lead", "quotation", "created_by")
            .prefetch_related("items")
        )

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, enum=list(Order.Status.values)),
            OpenApiParameter("customer", int, description="Exact Customer ID inside actor scope."),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=DocumentItemsSerializer, responses={200: OrderSerializer, **WRITE_RESPONSES})
    @action(detail=True, methods=["post"])
    def items(self, request, pk=None):
        serializer = DocumentItemsSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        document = replace_order_items(
            actor=request.user, order=self.get_object(), items=serializer.validated_data["items"]
        )
        return Response(self.get_serializer(document).data)

    @extend_schema(request=DocumentStatusTransitionSerializer, responses={200: OrderSerializer, **WRITE_RESPONSES})
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        serializer = DocumentStatusTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = transition_order(
            actor=request.user, order=self.get_object(), **serializer.validated_data
        )
        return Response(self.get_serializer(document).data)

    @extend_schema(
        request=ConvertOrderSerializer,
        responses={201: InvoiceSerializer, **WRITE_RESPONSES},
        description="Copies a confirmed order into a new draft invoice. The order is unchanged.",
    )
    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        serializer = ConvertOrderSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        invoice = convert_order_to_invoice(
            actor=request.user,
            order=self.get_object(),
            warehouse=serializer.validated_data.get("warehouse"),
        )
        return Response(
            InvoiceSerializer(invoice, context=self.get_serializer_context()).data, status=201
        )


class InvoiceViewSet(CommercialDocumentViewSet):
    required_feature = "invoices"
    required_capabilities = ("invoices.scoped", "invoices.company")
    queryset = Invoice.objects.none()
    serializer_class = InvoiceSerializer
    status_enum = Invoice.Status
    sensitive_actions = frozenset({"create", "update", "partial_update", "items", "issue", "cancel"})
    search_fields = ["number", "customer__full_name", "notes", "items__product_name_snapshot"]
    ordering_fields = ["created_at", "issued_at", "due_at", "total_amount", "number"]
    list_query_parameters = {"status", "customer", "settlement"}
    action_query_parameters = {"allocations": {"page"}}

    def get_queryset(self):
        queryset = self.filtered(
            invoices_for(self.request.user)
            .select_related("customer", "order", "quotation", "warehouse", "created_by")
            .prefetch_related("items")
        )
        settlement = self.request.query_params.get("settlement")
        if settlement is not None:
            if settlement not in Invoice.SettlementStatus.values:
                raise ValidationError({"settlement": "Unknown settlement status."})
            issued = queryset.filter(status=Invoice.Status.ISSUED)
            if settlement == Invoice.SettlementStatus.PAID:
                # `paid_amount` is capped at `total_amount` by a check
                # constraint, so equality is exactly "fully settled".
                queryset = issued.filter(paid_amount__gte=F("total_amount"))
            elif settlement == Invoice.SettlementStatus.UNPAID:
                queryset = issued.filter(paid_amount__lte=0)
            else:
                queryset = issued.filter(
                    paid_amount__gt=0, paid_amount__lt=F("total_amount")
                )
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, enum=list(Invoice.Status.values)),
            OpenApiParameter("customer", int, description="Exact Customer ID inside actor scope."),
            OpenApiParameter("settlement", str, enum=list(Invoice.SettlementStatus.values)),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=DocumentItemsSerializer, responses={200: InvoiceSerializer, **WRITE_RESPONSES})
    @action(detail=True, methods=["post"])
    def items(self, request, pk=None):
        serializer = DocumentItemsSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        document = replace_invoice_items(
            actor=request.user, invoice=self.get_object(), items=serializer.validated_data["items"]
        )
        return Response(self.get_serializer(document).data)

    @extend_schema(
        request=None,
        responses={200: InvoiceSerializer, **WRITE_RESPONSES},
        description=(
            "Makes the invoice final: snapshots unit cost, deducts stock when a warehouse is "
            "named, and posts the debit to the customer ledger, all in one transaction."
        ),
    )
    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        self._require_manager("Issuing an invoice is not allowed.")
        invoice = issue_invoice(actor=request.user, invoice=self.get_object())
        return Response(self.get_serializer(invoice).data)

    @extend_schema(request=ReasonSerializer, responses={200: InvoiceSerializer, **WRITE_RESPONSES})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        self._require_manager("Cancelling an invoice is not allowed.")
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = cancel_invoice(
            actor=request.user, invoice=self.get_object(), **serializer.validated_data
        )
        return Response(self.get_serializer(invoice).data)

    @extend_schema(responses={200: PaymentAllocationSerializer(many=True), 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE})
    @action(detail=True, methods=["get"])
    def allocations(self, request, pk=None):
        self._require_manager("Payment details are not visible to this role.")
        invoice = self.get_object()
        queryset = invoice.allocations.select_related("payment", "invoice", "created_by").all()
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(PaymentAllocationSerializer(page, many=True).data)


class PaymentViewSet(SensitiveActionThrottleMixin, StrictQueryParametersMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    required_feature = "payments"
    required_capabilities = ("payments.company",)
    permission_classes = [IsActiveAuthenticated, HasBillingCapability]
    queryset = Payment.objects.none()
    serializer_class = PaymentSerializer
    sensitive_actions = frozenset({"create", "allocate", "cancel", "release"})
    search_fields = ["number", "customer__full_name", "reference", "notes"]
    ordering_fields = ["received_at", "amount", "created_at", "number"]
    list_query_parameters = {"customer", "status", "method"}
    action_query_parameters = {"allocations": {"page"}}

    def get_queryset(self):
        queryset = payments_for(self.request.user).select_related("customer", "received_by")
        customer = self.request.query_params.get("customer")
        if customer is not None:
            if not customer.isdecimal() or int(customer) < 1:
                raise ValidationError({"customer": "Enter a positive integer."})
            queryset = queryset.filter(customer_id=int(customer))
        status_value = self.request.query_params.get("status")
        if status_value is not None:
            if status_value not in Payment.Status.values:
                raise ValidationError({"status": "Unknown status."})
            queryset = queryset.filter(status=status_value)
        method = self.request.query_params.get("method")
        if method is not None:
            if method not in Payment.Method.values:
                raise ValidationError({"method": "Unknown payment method."})
            queryset = queryset.filter(method=method)
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("customer", int, description="Exact Customer ID."),
            OpenApiParameter("status", str, enum=list(Payment.Status.values)),
            OpenApiParameter("method", str, enum=list(Payment.Method.values)),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=AllocatePaymentSerializer, responses={201: PaymentAllocationSerializer, **WRITE_RESPONSES})
    @action(detail=True, methods=["post"])
    def allocate(self, request, pk=None):
        serializer = AllocatePaymentSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        allocation = allocate_payment(
            actor=request.user, payment=self.get_object(), **serializer.validated_data
        )
        return Response(PaymentAllocationSerializer(allocation).data, status=201)

    @extend_schema(request=ReasonSerializer, responses={200: PaymentSerializer, **WRITE_RESPONSES})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = cancel_payment(
            actor=request.user, payment=self.get_object(), **serializer.validated_data
        )
        return Response(self.get_serializer(payment).data)

    @extend_schema(responses={200: PaymentAllocationSerializer(many=True), 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE})
    @action(detail=True, methods=["get"])
    def allocations(self, request, pk=None):
        payment = self.get_object()
        queryset = payment.allocations.select_related("payment", "invoice", "created_by").all()
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(PaymentAllocationSerializer(page, many=True).data)


class PaymentAllocationViewSet(SensitiveActionThrottleMixin, StrictQueryParametersMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    required_feature = "payments"
    required_capabilities = ("payments.company",)
    permission_classes = [IsActiveAuthenticated, HasBillingCapability]
    queryset = PaymentAllocation.objects.none()
    serializer_class = PaymentAllocationSerializer
    sensitive_actions = frozenset({"release"})
    ordering_fields = ["created_at", "amount"]
    list_query_parameters = {"invoice", "payment"}

    def get_queryset(self):
        queryset = PaymentAllocation.objects.filter(
            payment__in=payments_for(self.request.user)
        ).select_related("payment", "invoice", "created_by")
        for parameter, field in (("invoice", "invoice_id"), ("payment", "payment_id")):
            value = self.request.query_params.get(parameter)
            if value is not None:
                if not value.isdecimal() or int(value) < 1:
                    raise ValidationError({parameter: "Enter a positive integer."})
                queryset = queryset.filter(**{field: int(value)})
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("invoice", int, description="Exact Invoice ID."),
            OpenApiParameter("payment", int, description="Exact Payment ID."),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=ReasonSerializer, responses={200: PaymentAllocationSerializer, **WRITE_RESPONSES})
    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        allocation = release_allocation(
            actor=request.user, allocation=self.get_object(), **serializer.validated_data
        )
        return Response(self.get_serializer(allocation).data)


class ChequeViewSet(SensitiveActionThrottleMixin, StrictQueryParametersMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    required_feature = "payments"
    required_capabilities = ("payments.company",)
    permission_classes = [IsActiveAuthenticated, HasBillingCapability]
    queryset = Cheque.objects.none()
    serializer_class = ChequeSerializer
    sensitive_actions = frozenset({"transition"})
    search_fields = ["bank_name", "serial_number", "account_holder", "payment__customer__full_name"]
    ordering_fields = ["due_date", "amount", "created_at"]
    list_query_parameters = {"status", "customer"}
    action_query_parameters = {"history": {"page"}}

    def get_queryset(self):
        queryset = cheques_for(self.request.user).select_related("payment", "payment__customer")
        status_value = self.request.query_params.get("status")
        if status_value is not None:
            if status_value not in Cheque.Status.values:
                raise ValidationError({"status": "Unknown cheque status."})
            queryset = queryset.filter(status=status_value)
        customer = self.request.query_params.get("customer")
        if customer is not None:
            if not customer.isdecimal() or int(customer) < 1:
                raise ValidationError({"customer": "Enter a positive integer."})
            queryset = queryset.filter(payment__customer_id=int(customer))
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, enum=list(Cheque.Status.values)),
            OpenApiParameter("customer", int, description="Exact Customer ID."),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=ChequeTransitionSerializer, responses={200: ChequeSerializer, **WRITE_RESPONSES})
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        serializer = ChequeTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cheque = transition_cheque(
            actor=request.user, cheque=self.get_object(), **serializer.validated_data
        )
        return Response(self.get_serializer(cheque).data)

    @extend_schema(responses={200: ChequeStatusHistorySerializer(many=True), 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE})
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        cheque = self.get_object()
        queryset = cheque.history.select_related("changed_by").all()
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(ChequeStatusHistorySerializer(page, many=True).data)


class InstallmentPlanViewSet(SensitiveActionThrottleMixin, StrictQueryParametersMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    required_feature = "payments"
    required_capabilities = ("payments.company",)
    permission_classes = [IsActiveAuthenticated, HasBillingCapability]
    queryset = InstallmentPlan.objects.none()
    serializer_class = InstallmentPlanSerializer
    sensitive_actions = frozenset({"create", "cancel"})
    search_fields = ["invoice__number", "invoice__customer__full_name"]
    ordering_fields = ["created_at", "start_date", "total_amount"]
    list_query_parameters = {"status", "invoice"}

    def get_queryset(self):
        queryset = installment_plans_for(self.request.user).select_related(
            "invoice", "invoice__customer", "created_by"
        ).prefetch_related("installments")
        status_value = self.request.query_params.get("status")
        if status_value is not None:
            if status_value not in InstallmentPlan.Status.values:
                raise ValidationError({"status": "Unknown status."})
            queryset = queryset.filter(status=status_value)
        invoice = self.request.query_params.get("invoice")
        if invoice is not None:
            if not invoice.isdecimal() or int(invoice) < 1:
                raise ValidationError({"invoice": "Enter a positive integer."})
            queryset = queryset.filter(invoice_id=int(invoice))
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, enum=list(InstallmentPlan.Status.values)),
            OpenApiParameter("invoice", int, description="Exact Invoice ID."),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=CreateInstallmentPlanSerializer, responses={201: InstallmentPlanSerializer, **WRITE_RESPONSES})
    def create(self, request, *args, **kwargs):
        serializer = CreateInstallmentPlanSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if data.get("interval_days") is None:
            data.pop("interval_days", None)
        plan = create_installment_plan(actor=request.user, **data)
        return Response(
            InstallmentPlanSerializer(plan, context=self.get_serializer_context()).data, status=201
        )

    @extend_schema(request=ReasonSerializer, responses={200: InstallmentPlanSerializer, **WRITE_RESPONSES})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = cancel_installment_plan(
            actor=request.user, plan=self.get_object(), **serializer.validated_data
        )
        return Response(self.get_serializer(plan).data)


class InstallmentViewSet(StrictQueryParametersMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    required_feature = "payments"
    required_capabilities = ("payments.company",)
    permission_classes = [IsActiveAuthenticated, HasBillingCapability]
    queryset = Installment.objects.none()
    serializer_class = InstallmentSerializer
    ordering_fields = ["due_date", "amount", "sequence"]
    list_query_parameters = {"plan", "status", "due_before"}

    def get_queryset(self):
        queryset = installments_for(self.request.user).select_related("plan", "plan__invoice")
        plan = self.request.query_params.get("plan")
        if plan is not None:
            if not plan.isdecimal() or int(plan) < 1:
                raise ValidationError({"plan": "Enter a positive integer."})
            queryset = queryset.filter(plan_id=int(plan))
        status_value = self.request.query_params.get("status")
        if status_value is not None:
            if status_value not in Installment.Status.values:
                raise ValidationError({"status": "Unknown status."})
            queryset = queryset.filter(status=status_value)
        due_before = self.request.query_params.get("due_before")
        if due_before is not None:
            queryset = queryset.filter(due_date__lt=_parse_date(due_before, "due_before"))
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("plan", int, description="Exact InstallmentPlan ID."),
            OpenApiParameter("status", str, enum=list(Installment.Status.values)),
            OpenApiParameter("due_before", str, description="ISO date; installments due before it."),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class CustomerLedgerViewSet(SensitiveActionThrottleMixin, StrictQueryParametersMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    required_feature = "customer_ledger"
    required_capabilities = ("ledger.company",)
    permission_classes = [IsActiveAuthenticated, HasBillingCapability]
    queryset = CustomerLedgerEntry.objects.none()
    serializer_class = CustomerLedgerEntrySerializer
    sensitive_actions = frozenset({"opening_balance"})
    ordering_fields = ["occurred_at", "created_at"]
    list_query_parameters = {"customer", "entry_type"}
    action_query_parameters = {"balance": {"customer"}}

    def get_queryset(self):
        queryset = ledger_entries_for(self.request.user).select_related("customer", "created_by")
        customer = self.request.query_params.get("customer")
        if customer is not None:
            if not customer.isdecimal() or int(customer) < 1:
                raise ValidationError({"customer": "Enter a positive integer."})
            queryset = queryset.filter(customer_id=int(customer))
        entry_type = self.request.query_params.get("entry_type")
        if entry_type is not None:
            if entry_type not in CustomerLedgerEntry.EntryType.values:
                raise ValidationError({"entry_type": "Unknown entry type."})
            queryset = queryset.filter(entry_type=entry_type)
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("customer", int, description="Exact Customer ID."),
            OpenApiParameter("entry_type", str, enum=list(CustomerLedgerEntry.EntryType.values)),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        parameters=[OpenApiParameter("customer", int, required=True, description="Exact Customer ID.")],
        responses={200: None, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE},
        description="Current balance of one customer account: positive is owed to us.",
    )
    @action(detail=False, methods=["get"])
    def balance(self, request):
        customer = request.query_params.get("customer")
        if customer is None or not customer.isdecimal() or int(customer) < 1:
            raise ValidationError({"customer": "Enter a positive integer."})
        target = customers_for(request.user).filter(pk=int(customer)).first()
        if target is None:
            raise ValidationError({"customer": "Invalid object."})
        return Response({"customer": target.pk, "balance": str(current_balance(target))})

    @extend_schema(
        request=OpeningBalanceSerializer,
        responses={201: CustomerLedgerEntrySerializer, **WRITE_RESPONSES},
        description="Posts a balance carried in from before this system. Allowed once per customer.",
    )
    @action(detail=False, methods=["post"], url_path="opening-balance")
    def opening_balance(self, request):
        serializer = OpeningBalanceSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if data.get("occurred_at") is None:
            data.pop("occurred_at", None)
        entry = record_opening_balance(actor=request.user, **data)
        return Response(CustomerLedgerEntrySerializer(entry).data, status=201)


