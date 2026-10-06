"""`/api/v1/campaigns/` and `/api/v1/campaign-members/` (2.36.0)."""

import io
from datetime import date, timedelta

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from openpyxl import Workbook
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.access import has_any_capability
from accounts.models import User
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated
from common.throttles import SensitiveActionThrottleMixin
from common.viewsets import AdminHardDeleteModelViewSet
from reports.xlsx import safe_spreadsheet_text
from sales.campaign_analytics import campaign_analysis, campaign_rows, campaigns_for, members_for, unattributed_row
from sales.campaign_attribution import attribute_manually
from sales.campaigns import channel_labels
from sales.campaigns import (
    add_campaign_member,
    assign_campaign_member,
    create_campaign,
    ensure_customer_for_member,
    ensure_system_campaigns,
    set_campaign_status,
    set_member_stage,
    update_campaign,
)
from sales.models import Campaign, CampaignAttributionLog, TargetAudienceMember
from sales.permissions import HasSalesCapability


class CampaignSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    channels = serializers.ListField(child=serializers.ChoiceField(choices=Campaign.Channel.choices), required=False)
    channels_display = serializers.SerializerMethodField()
    #: What «سایر» is, in the operator's words (2.40.22).
    other_channels = serializers.ListField(
        child=serializers.CharField(max_length=60, allow_blank=True), required=False, max_length=10,
    )
    responsibles = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), many=True, required=False
    )
    responsibles_display = serializers.SerializerMethodField()
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Campaign.objects.filter(parent__isnull=True), required=False, allow_null=True
    )
    parent_name = serializers.CharField(source="parent.name", read_only=True, default="")
    children_count = serializers.SerializerMethodField()
    budget_warning = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    is_system = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            "id", "name", "parent", "parent_name", "children_count", "budget_warning", "status", "status_display", "channels", "other_channels", "channels_display", "starts_on", "ends_on",
            "target_count", "budget", "responsibles", "responsibles_display", "member_count", "is_system",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "status_display", "channels_display", "created_at", "updated_at"]

    def get_channels_display(self, instance) -> list:
        return channel_labels(instance)

    def get_responsibles_display(self, instance) -> list:
        return [user.get_full_name() or user.username for user in instance.responsibles.all()]

    def get_member_count(self, instance) -> int:
        return getattr(instance, "member_count_annotated", None) or instance.members.count()

    def get_children_count(self, instance) -> int:
        return instance.children.count()

    def get_budget_warning(self, instance) -> str | None:
        from sales.campaigns import budget_overshoot

        over = getattr(instance, "budget_warning", None)
        if over is None:
            over = budget_overshoot(instance.parent if instance.parent_id else instance)
        return str(over) if over else None

    def get_is_system(self, instance) -> bool:
        return bool(instance.system_key)

    def _budget_visible(self):
        request = self.context.get("request")
        return bool(request and has_any_capability(request.user, "campaigns.company"))

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self._budget_visible():
            data.pop("budget", None)
            data.pop("budget_warning", None)
        return data

    def validate_parent(self, value):
        if self.instance is not None and value != self.instance.parent:
            raise serializers.ValidationError("کمپین بعد از ساخت به والد دیگری منتقل نمی‌شود.")
        return value

    def create(self, validated_data):
        return create_campaign(actor=self.context["request"].user, **validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("parent", None)
        return update_campaign(actor=self.context["request"].user, campaign=instance, **validated_data)


class CampaignMemberSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    stage_display = serializers.CharField(source="get_stage_display", read_only=True)
    assigned_to_display = serializers.SerializerMethodField()

    class Meta:
        model = TargetAudienceMember
        fields = [
            "id", "campaign", "campaign_name", "full_name", "raw_phone", "stage", "stage_display", "lost_reason",
            "assigned_to", "assigned_to_display", "next_follow_up_at", "converted_at", "was_customer_on_entry",
            "status", "customer", "created_at",
        ]
        read_only_fields = fields

    def get_assigned_to_display(self, instance) -> str:
        user = instance.assigned_to
        return (user.get_full_name() or user.username) if user else ""


class AddMemberSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    raw_phone = serializers.CharField(max_length=40)
    notes = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True), required=False)


class StageSerializer(serializers.Serializer):
    stage = serializers.CharField()
    lost_reason = serializers.CharField(required=False, allow_blank=True, max_length=300)


class AssignSerializer(serializers.Serializer):
    to_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True))
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class AttributeInvoiceSerializer(serializers.Serializer):
    invoice = serializers.IntegerField()
    campaign = serializers.PrimaryKeyRelatedField(queryset=Campaign.objects.all())
    reason = serializers.CharField(max_length=500)


def _date_param(request, name):
    raw = request.query_params.get(name)
    if not raw:
        # The step-by-step page sends the shared range control's window
        # (2.40.23): an instant pair, read here as the Tehran days it covers
        # (the end is exclusive).
        instant = {"date_from": "period_start", "date_to": "period_end"}.get(name)
        stamp = request.query_params.get(instant) if instant else None
        if stamp:
            from django.utils import timezone
            from django.utils.dateparse import parse_datetime

            moment = parse_datetime(stamp)
            if moment is None or timezone.is_naive(moment):
                raise ValidationError({instant: "زمان باید با منطقهٔ زمانی باشد."})
            if name == "date_to":
                moment -= timedelta(microseconds=1)
            return timezone.localtime(moment).date()
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({name: "تاریخ باید به شکل YYYY-MM-DD باشد."}) from exc


def _ids_param(request):
    raw = request.query_params.get("campaigns", "")
    try:
        return [int(part) for part in raw.split(",") if part.strip()]
    except ValueError as exc:
        raise ValidationError({"campaigns": "شناسه‌ها باید عدد باشند."}) from exc


class CampaignViewSet(SensitiveActionThrottleMixin, AdminHardDeleteModelViewSet):
    required_feature = "campaigns"
    delete_capability = "campaigns.delete"
    required_capabilities = ("campaigns.scoped", "campaigns.company")
    required_write_capabilities = ("campaigns.manage",)
    permission_classes = [IsActiveAuthenticated, HasSalesCapability]
    queryset = Campaign.objects.none()
    serializer_class = CampaignSerializer
    sensitive_actions = frozenset({"create", "update", "partial_update", "set_status", "add_member", "attribute_invoice"})
    search_fields = ["name"]
    ordering_fields = ["name", "created_at", "starts_on"]
    list_query_parameters = {"status", "channel"}
    action_query_parameters = {
        "analytics": {"campaigns", "date_from", "date_to", "period_start", "period_end"},
        "results": {"campaigns", "date_from", "date_to"},
        "export": {"campaigns", "date_from", "date_to", "period_start", "period_end"},
        "members": {"stage", "page"},
        "attribution_log": {"invoice"},
    }

    def get_queryset(self):
        from django.db.models import Count

        queryset = campaigns_for(self.request.user).annotate(member_count_annotated=Count("members", distinct=True))
        status_value = self.request.query_params.get("status")
        if status_value:
            if status_value not in Campaign.Status.values:
                raise ValidationError({"status": "وضعیت نامعتبر است."})
            queryset = queryset.filter(status=status_value)
        channel = self.request.query_params.get("channel")
        if channel:
            if channel not in Campaign.Channel.values:
                raise ValidationError({"channel": "راه ارتباط نامعتبر است."})
            ids = [pk for pk, values in queryset.values_list("pk", "channels") if channel in (values or [])]
            queryset = queryset.filter(pk__in=ids)
        # A tree by default (2.39.21): each top-level campaign, newest first,
        # followed directly by its sub-campaigns. An explicit `ordering` wins.
        from django.db.models import F
        from django.db.models.functions import Coalesce

        return queryset.annotate(tree_root=Coalesce("parent_id", "id")).order_by(
            "-tree_root", F("parent_id").asc(nulls_first=True), "-created_at", "-id"
        )

    def list(self, request, *args, **kwargs):
        # Normally a no-op read: the three system campaigns exist after the first
        # manager's visit, and only then does a GET take the write path (2.39.24).
        if has_any_capability(request.user, "campaigns.manage") and (
            Campaign.objects.filter(system_key__in=["direct", "referral", "legacy"]).count() < 3
        ):
            ensure_system_campaigns(request.user)
        return super().list(request, *args, **kwargs)

    def _extra_delete_guard(self, request, instance):
        from common.exceptions import BusinessPermissionDenied

        if instance.system_key:
            raise BusinessPermissionDenied("کمپین سیستمی حذف نمی‌شود.")

    def _manager_only(self):
        if not has_any_capability(self.request.user, "campaigns.manage"):
            raise PermissionDenied("مدیریت کمپین‌ها مجاز نیست.")

    def create(self, request, *args, **kwargs):
        self._manager_only()
        return super().create(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._manager_only()
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(request=StageSerializer, responses={200: CampaignSerializer})
    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        self._manager_only()
        value = request.data.get("status", "")
        campaign = set_campaign_status(actor=request.user, campaign=self.get_object(), status=value)
        return Response(self.get_serializer(campaign).data)

    @extend_schema(request=AddMemberSerializer, responses={201: CampaignMemberSerializer})
    @action(detail=True, methods=["post"], url_path="add-member")
    def add_member(self, request, pk=None):
        body = AddMemberSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        member = add_campaign_member(actor=request.user, campaign=self.get_object(), **body.validated_data)
        return Response(CampaignMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: CampaignMemberSerializer(many=True)})
    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        campaign = self.get_object()
        queryset = members_for(request.user).filter(campaign=campaign).select_related("campaign", "assigned_to")
        stage = request.query_params.get("stage")
        if stage:
            if stage not in TargetAudienceMember.Stage.values:
                raise ValidationError({"stage": "مرحله نامعتبر است."})
            queryset = queryset.filter(stage=stage)
        queryset = queryset.order_by("full_name", "id")
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(CampaignMemberSerializer(page, many=True).data)

    @action(detail=False, methods=["get"])
    def results(self, request):
        with_money = has_any_capability(request.user, "campaigns.company")
        rows = campaign_rows(
            request.user, ids=_ids_param(request), date_from=_date_param(request, "date_from"),
            date_to=_date_param(request, "date_to"), with_money=with_money,
        )
        # «بدون کمپین» closes the sum to the company's figures (2.40.0); only
        # when no campaign filter narrows the view.
        if with_money and not _ids_param(request):
            rows.append(unattributed_row(
                request.user, date_from=_date_param(request, "date_from"), date_to=_date_param(request, "date_to"),
            ))
        return Response({"results": rows, "with_money": with_money})

    @action(detail=False, methods=["get"])
    def analytics(self, request):
        if not has_any_capability(request.user, "campaigns.analytics"):
            raise PermissionDenied("تحلیل کمپین برای نقش شما فعال نیست.")
        data = campaign_analysis(
            request.user, ids=_ids_param(request),
            date_from=_date_param(request, "date_from"), date_to=_date_param(request, "date_to"),
        )
        if has_any_capability(request.user, "campaigns.company") and not _ids_param(request):
            data["campaigns"].append(unattributed_row(
                request.user, date_from=_date_param(request, "date_from"), date_to=_date_param(request, "date_to"),
            ))
        return Response(data)

    @action(detail=False, methods=["get"])
    def export(self, request):
        if not has_any_capability(request.user, "campaigns.analytics"):
            raise PermissionDenied("خروجی تحلیل کمپین برای نقش شما فعال نیست.")
        rows = campaign_rows(
            request.user, ids=_ids_param(request), date_from=_date_param(request, "date_from"),
            date_to=_date_param(request, "date_to"),
        )
        if has_any_capability(request.user, "campaigns.company") and not _ids_param(request):
            rows.append(unattributed_row(
                request.user, date_from=_date_param(request, "date_from"), date_to=_date_param(request, "date_to"),
            ))
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "campaigns"
        sheet.append([
            "کمپین", "وضعیت", "کانال", "اعضا", "تماس گرفته‌شده", "در تعامل", "تبدیل‌شده", "از قبل مشتری",
            "نرخ تبدیل (٪)", "فروش ثبت‌شده (تعداد)", "فروش ثبت‌شده (مبلغ)", "فاکتور معتبر (تعداد)",
            "فاکتور معتبر (مبلغ)", "وصول‌شده", "مانده", "بودجه",
        ])
        for row in rows:
            sheet.append([
                safe_spreadsheet_text(row["name"]), row["status_display"], row["channel_display"], row["members"],
                row["contacted"], row["engaged"], row["converted"], row["already_customers"],
                row["conversion_rate"] if row["conversion_rate"] is not None else "",
                row["registered_sales_count"], float(row["registered_sales_amount"]),
                row["valid_invoices_count"], float(row["valid_invoices_amount"]), float(row["collected_amount"]),
                float(row["remaining_amount"]),
                float(row["budget"]) if row["budget"] is not None else "",
            ])
        stream = io.BytesIO()
        workbook.save(stream)
        response = HttpResponse(
            stream.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename="campaigns.xlsx"'
        return response

    @extend_schema(request=AttributeInvoiceSerializer, responses={200: None})
    @action(detail=False, methods=["post"], url_path="attribute-invoice")
    def attribute_invoice(self, request):
        from billing.models import Invoice

        body = AttributeInvoiceSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        invoice = Invoice.objects.filter(pk=body.validated_data["invoice"]).first()
        if invoice is None:
            raise NotFound("فاکتور پیدا نشد.")
        attribution = attribute_manually(
            actor=request.user, invoice=invoice, campaign=body.validated_data["campaign"],
            reason=body.validated_data["reason"],
        )
        return Response({"invoice": invoice.pk, "campaign": attribution.campaign_id, "source": attribution.source})

    @action(detail=False, methods=["get"], url_path="attribution-log")
    def attribution_log(self, request):
        if not has_any_capability(request.user, "campaigns.attribute"):
            raise PermissionDenied("مشاهدهٔ تاریخچهٔ انتساب مجاز نیست.")
        invoice = request.query_params.get("invoice")
        if not invoice or not invoice.isdigit():
            raise ValidationError({"invoice": "شناسهٔ فاکتور را بدهید."})
        rows = CampaignAttributionLog.objects.filter(invoice_id=int(invoice)).select_related("from_campaign", "to_campaign", "actor")
        return Response({"results": [
            {
                "from": row.from_campaign.name if row.from_campaign else None,
                "to": row.to_campaign.name if row.to_campaign else None,
                "source": row.source,
                "actor": (row.actor.get_full_name() or row.actor.username) if row.actor else None,
                "reason": row.reason,
                "at": row.created_at,
            }
            for row in rows
        ]})


class CampaignMemberViewSet(FeatureGatedAPIMixin, SensitiveActionThrottleMixin, viewsets.GenericViewSet):
    required_feature = "campaigns"
    required_capabilities = ("campaigns.scoped", "campaigns.company")
    #: A marketer may move their own people between stages (`campaigns.work`);
    #: the service re-checks that the person is theirs.
    required_write_capabilities = ("campaigns.manage", "campaigns.work")
    permission_classes = [IsActiveAuthenticated, HasSalesCapability]
    queryset = TargetAudienceMember.objects.none()
    serializer_class = CampaignMemberSerializer
    sensitive_actions = frozenset({"stage", "assign", "customer"})

    def get_queryset(self):
        return members_for(self.request.user).select_related("campaign", "assigned_to")

    @extend_schema(request=StageSerializer, responses={200: CampaignMemberSerializer})
    @action(detail=True, methods=["post"])
    def stage(self, request, pk=None):
        body = StageSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        member = set_member_stage(actor=request.user, member=self.get_object(), **body.validated_data)
        return Response(CampaignMemberSerializer(member).data)

    @extend_schema(responses={200: CampaignMemberSerializer(many=True)})
    @action(detail=False, methods=["get"])
    def prospects(self, request):
        """People not yet linked to a customer, for the invoice wizard's
        «انتخاب از اشخاص کمپین» (2.40.0). Caller's member scope; at most 500."""
        rows = (
            self.get_queryset().filter(customer__isnull=True)
            .exclude(stage=TargetAudienceMember.Stage.LOST)
            .order_by("full_name", "id")[:500]
        )
        return Response(CampaignMemberSerializer(rows, many=True).data)

    @extend_schema(responses={200: CampaignMemberSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="follow-ups")
    def follow_ups(self, request):
        """Campaign people with a follow-up in [follow_up_from, follow_up_to) —
        the follow-up calendar's second source (2.39.25). Same scope as the
        list: a marketer gets only the people assigned to them. At most 500."""
        from django.utils import timezone
        from django.utils.dateparse import parse_datetime

        bounds = {}
        for name in ("follow_up_from", "follow_up_to"):
            raw = request.query_params.get(name)
            value = parse_datetime(raw) if raw else None
            if raw and (value is None or timezone.is_naive(value)):
                raise ValidationError({name: "زمان را با منطقهٔ زمانی (ISO 8601) بفرستید."})
            bounds[name] = value
        queryset = (
            self.get_queryset()
            .filter(next_follow_up_at__isnull=False)
            .exclude(stage__in=[TargetAudienceMember.Stage.LOST, TargetAudienceMember.Stage.CONVERTED])
        )
        if bounds["follow_up_from"]:
            queryset = queryset.filter(next_follow_up_at__gte=bounds["follow_up_from"])
        if bounds["follow_up_to"]:
            queryset = queryset.filter(next_follow_up_at__lt=bounds["follow_up_to"])
        rows = queryset.order_by("next_follow_up_at", "id")[:500]
        return Response(CampaignMemberSerializer(rows, many=True).data)

    @extend_schema(request=None, responses={200: CampaignMemberSerializer})
    @action(detail=True, methods=["post"], url_path="customer")
    def customer(self, request, pk=None):
        member = ensure_customer_for_member(actor=request.user, member=self.get_object())
        return Response(CampaignMemberSerializer(member).data)

    @extend_schema(request=AssignSerializer, responses={200: CampaignMemberSerializer})
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        body = AssignSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        member = assign_campaign_member(actor=request.user, member=self.get_object(), to_user=body.validated_data["to_user"], reason=body.validated_data.get("reason", ""))
        return Response(CampaignMemberSerializer(member).data)
