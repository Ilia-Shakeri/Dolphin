from rest_framework import serializers

from accounts.access import crm_identities
from accounts.models import User
from aftersales.models import AfterSalesHistory, AfterSalesRequest, CaseType
from aftersales.services import create_after_sales_request
from common.serializers import RejectServerFieldsMixin
from sales.models import Customer, Sale, SalesDocument


DEADLINE_FIELDS = ("response_due", "plan_due", "resolution_due", "responded_at", "planned_at")


class AfterSalesRequestSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"customer_name", "assigned_to_display", "created_by", "created_by_display", "closed_at", "next_appointment_at", "created_at", "updated_at", "final_result", *DEADLINE_FIELDS}
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    assigned_to_display = serializers.SerializerMethodField()
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_display = serializers.SerializerMethodField()
    #: 2.40.60 (BIZ-008): a type, a priority and a starting stage on create;
    #: after that each moves through its own action, which keeps the history.
    #: `status` is the stage's name; the free words of before are optional.
    status = serializers.CharField(max_length=80, required=False, allow_blank=True)
    case_type = serializers.PrimaryKeyRelatedField(queryset=CaseType.objects.filter(is_active=True), required=False, allow_null=True)
    case_type_label = serializers.SerializerMethodField()
    stage = serializers.CharField(max_length=40, required=False, allow_blank=True)
    stage_label = serializers.SerializerMethodField()
    stage_kind = serializers.SerializerMethodField()
    priority = serializers.ChoiceField(choices=["normal", "urgent", "critical"], required=False)
    priority_label = serializers.SerializerMethodField()
    final_result_label = serializers.SerializerMethodField()
    #: Which deadline has passed unmet, for the badge beside it.
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = AfterSalesRequest
        fields = [
            "id", "customer", "customer_name", "sale", "document", "subject", "description",
            "status", "case_type", "case_type_label", "stage", "stage_label", "stage_kind", "priority", "priority_label",
            "final_result", "final_result_label", "response_due", "plan_due", "resolution_due", "responded_at",
            "planned_at", "overdue", "assigned_to", "assigned_to_display", "created_by", "created_by_display",
            "closed_at", "next_appointment_at", "created_at", "updated_at",
        ]
        # next_appointment_at is read-only here on purpose: it changes only
        # through schedule_after_sales_appointment (the schedule-appointment
        # action below), never through a plain create/update, so its own
        # permission rule (elevated, or the assigned technician) cannot be
        # bypassed by writing the field directly on this serializer.
        read_only_fields = ["id", "customer_name", "assigned_to_display", "created_by", "created_by_display", "closed_at", "next_appointment_at", "created_at", "updated_at", "final_result", *DEADLINE_FIELDS]

    def _stage(self, instance):
        cache = self.context.setdefault("_case_stages", {})
        key = instance.case_type_id
        if key not in cache:
            from aftersales.workflow import stages_for

            cache[key] = {stage.key: stage for stage in stages_for(instance.case_type)}
        return cache[key].get(instance.stage)

    def get_case_type_label(self, instance) -> str:
        return instance.case_type.label if instance.case_type_id else ""

    def get_stage_label(self, instance) -> str:
        stage = self._stage(instance)
        return stage.label if stage else instance.status

    def get_stage_kind(self, instance) -> str:
        stage = self._stage(instance)
        return stage.kind if stage else ("closed" if instance.closed_at else "open")

    def get_priority_label(self, instance) -> str:
        from aftersales.workflow import PRIORITY_LABELS

        return PRIORITY_LABELS.get(instance.priority, instance.priority)

    def get_final_result_label(self, instance) -> str:
        from aftersales.workflow import RESULT_LABELS

        return RESULT_LABELS.get(instance.final_result, "")

    def get_overdue(self, instance) -> list[str]:
        from django.utils import timezone

        if instance.closed_at is not None:
            return []
        now = timezone.now()
        late = []
        if instance.response_due and instance.responded_at is None and instance.response_due < now:
            late.append("response")
        if instance.plan_due and instance.planned_at is None and instance.plan_due < now:
            late.append("plan")
        if instance.resolution_due and instance.resolution_due < now:
            late.append("resolution")
        return late

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated and request.user.role in {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}:
            self.fields["customer"].queryset = Customer.objects.all()
            self.fields["sale"].queryset = Sale.objects.all()
            self.fields["document"].queryset = SalesDocument.objects.all()
            self.fields["assigned_to"].queryset = crm_identities(User.objects.filter(
                role=User.Role.SALES_AGENT, workstream=User.Workstream.AFTER_SALES, is_active=True,
            ))
        else:
            self.fields["customer"].queryset = Customer.objects.none()
            self.fields["sale"].queryset = Sale.objects.none()
            self.fields["document"].queryset = SalesDocument.objects.none()
            self.fields["assigned_to"].queryset = User.objects.none()

    def get_assigned_to_display(self, instance) -> str | None:
        return instance.assigned_to and (instance.assigned_to.get_full_name() or instance.assigned_to.username)

    def get_created_by_display(self, instance) -> str:
        return instance.created_by.get_full_name() or instance.created_by.username

    def create(self, validated_data):
        return create_after_sales_request(actor=self.context["request"].user, **validated_data)


class AssignmentSerializer(RejectServerFieldsMixin, serializers.Serializer):
    to_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.none())
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["to_user"].queryset = crm_identities(User.objects.filter(
            role=User.Role.SALES_AGENT, workstream=User.Workstream.AFTER_SALES, is_active=True,
        ))


class AfterSalesAssigneeSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    display = serializers.CharField(read_only=True)


class StatusTransitionSerializer(RejectServerFieldsMixin, serializers.Serializer):
    to_status = serializers.CharField(max_length=80)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class CloseSerializer(RejectServerFieldsMixin, serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
    #: 2.40.60: «حل‌شده» (resolved), «حل‌نشده» (unresolved) or «مختومه با توافق مشتری» (agreed).
    final_result = serializers.CharField(max_length=12, required=False, allow_blank=True)


class ReopenSerializer(RejectServerFieldsMixin, serializers.Serializer):
    reason = serializers.CharField(max_length=500, allow_blank=True)
    to_stage = serializers.CharField(max_length=40, required=False, allow_blank=True)


class PrioritySerializer(RejectServerFieldsMixin, serializers.Serializer):
    priority = serializers.CharField(max_length=10)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class PlanSerializer(RejectServerFieldsMixin, serializers.Serializer):
    note = serializers.CharField(max_length=500, allow_blank=True)


class AppointmentSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """`appointment_at=null` clears a previously scheduled appointment."""

    appointment_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class AfterSalesHistorySerializer(serializers.ModelSerializer):
    actor_display = serializers.SerializerMethodField()
    from_user_display = serializers.SerializerMethodField()
    to_user_display = serializers.SerializerMethodField()

    class Meta:
        model = AfterSalesHistory
        fields = ["id", "request", "event", "actor", "actor_display", "from_status", "to_status", "from_user", "from_user_display", "to_user", "to_user_display", "appointment_at", "reason", "created_at"]
        read_only_fields = fields

    def _display(self, user) -> str | None:
        return user and (user.get_full_name() or user.username)

    def get_actor_display(self, instance) -> str | None: return self._display(instance.actor)
    def get_from_user_display(self, instance) -> str | None: return self._display(instance.from_user)
    def get_to_user_display(self, instance) -> str | None: return self._display(instance.to_user)
