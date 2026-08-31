from django.db.models import F, Q
from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.access import has_any_capability
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
    set_cheque_registration,
    spend_received_cheque,
    allocate_payment,
    allocate_payment_across,
    cancel_installment_plan,
    cancel_payment,
    create_installment_plan,
    record_opening_balance,
    release_allocation,
    transition_cheque,
    update_payment,
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
    InvoiceOrderLinkSerializer,
    ManualPaidEntrySerializer,
    AllocatePaymentAcrossSerializer,
    AllocatePaymentSerializer,
    ChequeSerializer,
    ChequeRegistrationSerializer,
    ChequeSpendSerializer,
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
    PaymentCorrectionSerializer,
    PaymentAllocationSerializer,
    PaymentSerializer,
    QuotationSerializer,
    ReasonSerializer,
    DocumentStatusTransitionSerializer,
)
from billing.services import (
    link_invoice_to_order,
    record_manual_paid_entry,
    cancel_invoice,
    reissue_invoice,
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
        raise ValidationError({field: "تاریخ معتبر به قالب ISO وارد کنید."})
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
                raise ValidationError({"status": "وضعیت نامعتبر است."})
            queryset = queryset.filter(status=status_value)
        customer = self.request.query_params.get("customer")
        if customer is not None:
            if not customer.isdecimal() or int(customer) < 1:
                raise ValidationError({"customer": "یک عدد صحیح مثبت وارد کنید."})
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
    sensitive_actions = frozenset({
        "create", "update", "partial_update", "items", "issue", "cancel",
        "reissue", "manual_paid", "link_order",
    })
    search_fields = ["number", "customer__full_name", "notes", "items__product_name_snapshot"]
    ordering_fields = ["created_at", "issued_at", "due_at", "total_amount", "number"]
    #: `order` lets the order page list the invoices linked to it through the
    #: real relation rather than by matching document numbers as text.
    list_query_parameters = {"status", "customer", "settlement", "order"}
    action_query_parameters = {"allocations": {"page"}}

    def get_queryset(self):
        queryset = self.filtered(
            invoices_for(self.request.user)
            .select_related("customer", "order", "quotation", "warehouse", "created_by")
            .prefetch_related("items")
        )
        order = self.request.query_params.get("order")
        if order is not None:
            if not str(order).isdigit():
                raise ValidationError({"order": "شناسه عددی سفارش را وارد کنید."})
            queryset = queryset.filter(order_id=int(order))
        # Official against unofficial is the split a reader of this list works
        # in, so it is a filter rather than something to find by scanning.
        invoice_type = self.request.query_params.get("invoice_type")
        if invoice_type is not None:
            if invoice_type not in Invoice.InvoiceType.values:
                raise ValidationError({"invoice_type": "نوع فاکتور نامعتبر است."})
            queryset = queryset.filter(invoice_type=invoice_type)
        settlement = self.request.query_params.get("settlement")
        if settlement is not None:
            if settlement not in Invoice.SettlementStatus.values:
                raise ValidationError({"settlement": "وضعیت تسویه نامعتبر است."})
            issued = queryset.filter(status=Invoice.Status.ISSUED)
            # A manually settled invoice reads as settled everywhere, so the
            # filter has to agree with what the document itself shows.
            manually_settled = Q(manual_settled_at__isnull=False)
            if settlement == Invoice.SettlementStatus.PAID:
                # `paid_amount` is capped at `total_amount` by a check
                # constraint, so equality is exactly "fully settled".
                queryset = issued.filter(Q(paid_amount__gte=F("total_amount")) | manually_settled)
            elif settlement == Invoice.SettlementStatus.UNPAID:
                queryset = issued.filter(paid_amount__lte=0).exclude(manually_settled)
            else:
                queryset = issued.filter(
                    paid_amount__gt=0, paid_amount__lt=F("total_amount")
                ).exclude(manually_settled)
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, enum=list(Invoice.Status.values)),
            OpenApiParameter("customer", int, description="Exact Customer ID inside actor scope."),
            OpenApiParameter("settlement", str, enum=list(Invoice.SettlementStatus.values)),
            OpenApiParameter("invoice_type", str, enum=list(Invoice.InvoiceType.values)),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=ManualPaidEntrySerializer,
        responses={200: InvoiceSerializer, **WRITE_RESPONSES},
        description=(
            "Record the typed پرداخت شده figure. Entering exactly the amount the payment "
            "records still show outstanding marks the invoice settled, once and for good. It "
            "creates no Payment, allocation or ledger entry and never changes `paid_amount`, so "
            "receivables and the customer ledger are unaffected."
        ),
    )
    @action(detail=True, methods=["post"], url_path="manual-paid")
    def manual_paid(self, request, pk=None):
        serializer = ManualPaidEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = record_manual_paid_entry(
            actor=request.user,
            invoice=self.get_object(),
            amount=serializer.validated_data["amount"],
        )
        return Response(self.get_serializer(invoice).data)

    @extend_schema(
        request=InvoiceOrderLinkSerializer,
        responses={200: InvoiceSerializer, **WRITE_RESPONSES},
        description=(
            "Attach this invoice to an existing order, or detach it with null. Client-1 raises "
            "the invoice first, so the two documents normally exist before anyone knows they "
            "belong together. One order may gather several invoices."
        ),
    )
    @action(detail=True, methods=["post"], url_path="link-order")
    def link_order(self, request, pk=None):
        serializer = InvoiceOrderLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = link_invoice_to_order(
            actor=request.user,
            invoice=self.get_object(),
            order=serializer.validated_data["order"],
        )
        return Response(self.get_serializer(invoice).data)

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
        self._require_manager("صدور فاکتور مجاز نیست.")
        invoice = issue_invoice(actor=request.user, invoice=self.get_object())
        return Response(self.get_serializer(invoice).data)

    @extend_schema(request=ReasonSerializer, responses={200: InvoiceSerializer, **WRITE_RESPONSES})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        self._require_manager("لغو فاکتور مجاز نیست.")
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = cancel_invoice(
            actor=request.user, invoice=self.get_object(), **serializer.validated_data
        )
        return Response(self.get_serializer(invoice).data)

    @extend_schema(request=ReasonSerializer, responses={201: InvoiceSerializer, **WRITE_RESPONSES})
    @action(detail=True, methods=["post"])
    def reissue(self, request, pk=None):
        """بند ۸.۲ — cancel this invoice and raise a replacement draft."""
        self._require_manager("صدور مجدد فاکتور مجاز نیست.")
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        replacement = reissue_invoice(
            actor=request.user, invoice=self.get_object(), **serializer.validated_data
        )
        return Response(self.get_serializer(replacement).data, status=201)

    @extend_schema(responses={200: PaymentAllocationSerializer(many=True), 403: ACCESS_DENIED_RESPONSE, 404: NOT_FOUND_RESPONSE})
    @action(detail=True, methods=["get"])
    def allocations(self, request, pk=None):
        if not has_any_capability(self.request.user, "payments.company"):
            raise PermissionDenied("جزئیات پرداخت برای این نقش قابل مشاهده نیست.")
        invoice = self.get_object()
        queryset = invoice.allocations.select_related("payment", "invoice", "created_by").all()
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(PaymentAllocationSerializer(page, many=True).data)


class PaymentViewSet(SensitiveActionThrottleMixin, StrictQueryParametersMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    required_feature = "payments"
    required_capabilities = ("payments.company",)
    required_write_capabilities = ("payments.manage",)
    permission_classes = [IsActiveAuthenticated, HasBillingCapability]
    queryset = Payment.objects.none()
    serializer_class = PaymentSerializer
    sensitive_actions = frozenset({
        "create", "allocate", "allocate_across", "cancel", "release", "correct",
    })
    search_fields = ["number", "customer__full_name", "reference", "notes"]
    ordering_fields = ["received_at", "amount", "created_at", "number"]
    #: `direction` joined these in 1.3.x. It became a first-class field in
    #: 1.2.1 and the list already charts by it, but the endpoint refused to
    #: filter on it — so "show me only the money that went out" was a question
    #: the API could not answer about a column it stores.
    list_query_parameters = {"customer", "status", "method", "direction", "desk"}
    action_query_parameters = {"allocations": {"page"}}

    def get_queryset(self):
        # `cheque` is a reverse one-to-one and `cheque__payment__customer`
        # feeds the nested cheque representation; without both, each row costs
        # extra queries.
        queryset = payments_for(self.request.user).select_related(
            "customer", "received_by", "cheque", "cheque__payment", "cheque__payment__customer"
        )
        customer = self.request.query_params.get("customer")
        if customer is not None:
            if not customer.isdecimal() or int(customer) < 1:
                raise ValidationError({"customer": "یک عدد صحیح مثبت وارد کنید."})
            queryset = queryset.filter(customer_id=int(customer))
        status_value = self.request.query_params.get("status")
        if status_value is not None:
            if status_value not in Payment.Status.values:
                raise ValidationError({"status": "وضعیت نامعتبر است."})
            queryset = queryset.filter(status=status_value)
        direction = self.request.query_params.get("direction")
        if direction is not None:
            if direction not in Payment.Direction.values:
                raise ValidationError({"direction": "جهت نامعتبر است."})
            queryset = queryset.filter(direction=direction)

        # `desk` is what the two screens ask for, and it is not the same
        # question as `direction`.
        #
        # A cheque taken in from a customer and later handed to someone else is
        # **one document**, and it belongs on both desks: it is still the receipt
        # that was recorded, and it is also money that has left. So the paying
        # desk asks for disbursements *plus* the receipts whose cheque was spent.
        #
        # It is a second view of the same row, never a second row. Recording a
        # disbursement for the endorsement would count the same money twice and
        # would debit a customer for a cheque that was never ours — which is why
        # `spend_received_cheque` creates nothing, and why this is a query rather
        # than a document.
        desk = self.request.query_params.get("desk")
        if desk is not None:
            if desk not in Payment.Direction.values:
                raise ValidationError({"desk": "باجه نامعتبر است."})
            if desk == Payment.Direction.DISBURSEMENT:
                queryset = queryset.filter(
                    Q(direction=Payment.Direction.DISBURSEMENT)
                    | Q(cheque__status=Cheque.Status.SPENT)
                )
            else:
                queryset = queryset.filter(direction=Payment.Direction.RECEIPT)
        method = self.request.query_params.get("method")
        if method is not None:
            if method not in Payment.Method.values:
                raise ValidationError({"method": "روش پرداخت نامعتبر است."})
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

    @extend_schema(
        request=AllocatePaymentAcrossSerializer,
        responses={201: PaymentAllocationSerializer(many=True), **WRITE_RESPONSES},
    )
    @action(detail=True, methods=["post"], url_path="allocate-across")
    def allocate_across(self, request, pk=None):
        """Settle several invoices from one receipt in a single transaction."""
        serializer = AllocatePaymentAcrossSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        allocations = allocate_payment_across(
            actor=request.user,
            payment=self.get_object(),
            splits=serializer.validated_data["splits"],
        )
        return Response(
            PaymentAllocationSerializer(allocations, many=True).data, status=201
        )

    @extend_schema(
        request=PaymentCorrectionSerializer,
        responses={200: PaymentSerializer, **WRITE_RESPONSES},
        description=(
            "Correct a recorded payment. Platform admin only, and enforced in the "
            "service as well as here. If the amount or the customer changes on a "
            "confirmed payment the ledger is restated rather than rewritten: the old "
            "entry is reversed and the new one posted, so both movements stay visible."
        ),
    )
    @action(detail=True, methods=["post"], url_path="correct")
    def correct(self, request, pk=None):
        serializer = PaymentCorrectionSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        payment = update_payment(
            actor=request.user, payment=self.get_object(), **serializer.validated_data
        )
        return Response(self.get_serializer(payment).data)

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
    required_write_capabilities = ("payments.manage",)
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
                    raise ValidationError({parameter: "یک عدد صحیح مثبت وارد کنید."})
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
    required_write_capabilities = ("payments.manage",)
    permission_classes = [IsActiveAuthenticated, HasBillingCapability]
    queryset = Cheque.objects.none()
    serializer_class = ChequeSerializer
    sensitive_actions = frozenset({"transition", "spend", "registration"})
    search_fields = ["bank_name", "serial_number", "account_holder", "payment__customer__full_name"]
    ordering_fields = ["due_date", "amount", "created_at"]
    list_query_parameters = {"status", "customer", "is_registered"}
    action_query_parameters = {"history": {"page"}}

    def get_queryset(self):
        queryset = cheques_for(self.request.user).select_related("payment", "payment__customer")
        status_value = self.request.query_params.get("status")
        if status_value is not None:
            if status_value not in Cheque.Status.values:
                raise ValidationError({"status": "وضعیت چک نامعتبر است."})
            queryset = queryset.filter(status=status_value)
        # حالت is the axis that is not وضعیت, so it filters separately rather
        # than as another value of `status`. Only the two literals are accepted;
        # anything else would quietly become False and silently narrow the list.
        registered = self.request.query_params.get("is_registered")
        if registered is not None:
            if registered not in {"true", "false"}:
                raise ValidationError({"is_registered": "مقدار «true» یا «false» را وارد کنید."})
            queryset = queryset.filter(is_registered=(registered == "true"))
        customer = self.request.query_params.get("customer")
        if customer is not None:
            if not customer.isdecimal() or int(customer) < 1:
                raise ValidationError({"customer": "یک عدد صحیح مثبت وارد کنید."})
            queryset = queryset.filter(payment__customer_id=int(customer))
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, enum=list(Cheque.Status.values)),
            OpenApiParameter("is_registered", str, enum=["true", "false"], description="حالت."),
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

    @extend_schema(
        request=ChequeRegistrationSerializer,
        responses={200: ChequeSerializer, **WRITE_RESPONSES},
        description=(
            "Move حالت — whether the cheque has been registered. This is the other "
            "axis, and it moves on its own: registering an instrument records where "
            "the paper is, not whether the money arrived, so it never credits, "
            "cancels, or otherwise touches the payment underneath."
        ),
    )
    @action(detail=True, methods=["post"])
    def registration(self, request, pk=None):
        serializer = ChequeRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cheque = set_cheque_registration(
            actor=request.user, cheque=self.get_object(), **serializer.validated_data
        )
        return Response(self.get_serializer(cheque).data)

    @extend_schema(
        request=ChequeSpendSerializer,
        responses={200: ChequeSerializer, **WRITE_RESPONSES},
        description=(
            "Endorse a received cheque to a third party. This changes the cheque that "
            "already exists and creates nothing: the instrument handed over is the "
            "instrument recorded, so it is never counted twice. The underlying payment "
            "ends, because the money is not arriving through it any more."
        ),
    )
    @action(detail=True, methods=["post"])
    def spend(self, request, pk=None):
        serializer = ChequeSpendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cheque = spend_received_cheque(
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
    required_write_capabilities = ("payments.manage",)
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
                raise ValidationError({"status": "وضعیت نامعتبر است."})
            queryset = queryset.filter(status=status_value)
        invoice = self.request.query_params.get("invoice")
        if invoice is not None:
            if not invoice.isdecimal() or int(invoice) < 1:
                raise ValidationError({"invoice": "یک عدد صحیح مثبت وارد کنید."})
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
                raise ValidationError({"plan": "یک عدد صحیح مثبت وارد کنید."})
            queryset = queryset.filter(plan_id=int(plan))
        status_value = self.request.query_params.get("status")
        if status_value is not None:
            if status_value not in Installment.Status.values:
                raise ValidationError({"status": "وضعیت نامعتبر است."})
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
    #: Either capability opens the endpoint; `ledger_entries_for` decides which
    #: rows come back. A marketer holds only `ledger.own` and so sees only their
    #: own customers' movements.
    required_capabilities = ("ledger.company", "ledger.own")
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
                raise ValidationError({"customer": "یک عدد صحیح مثبت وارد کنید."})
            queryset = queryset.filter(customer_id=int(customer))
        entry_type = self.request.query_params.get("entry_type")
        if entry_type is not None:
            if entry_type not in CustomerLedgerEntry.EntryType.values:
                raise ValidationError({"entry_type": "نوع سند نامعتبر است."})
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
            raise ValidationError({"customer": "یک عدد صحیح مثبت وارد کنید."})
        target = customers_for(request.user).filter(pk=int(customer)).first()
        if target is None:
            raise ValidationError({"customer": "مورد نامعتبر است."})
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


