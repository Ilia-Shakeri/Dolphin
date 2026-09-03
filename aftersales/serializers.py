from rest_framework import serializers

from accounts.access import crm_identities
from accounts.models import User
from aftersales.models import AfterSalesHistory, AfterSalesRequest
from aftersales.services import create_after_sales_request
from common.serializers import RejectServerFieldsMixin
from sales.models import Customer, Sale, SalesDocument


class AfterSalesRequestSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"customer_name", "assigned_to_display", "created_by", "created_by_display", "closed_at", "next_appointment_at", "created_at", "updated_at"}
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    assigned_to_display = serializers.SerializerMethodField()
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_display = serializers.SerializerMethodField()

    class Meta:
        model = AfterSalesRequest
        fields = [
            "id", "customer", "customer_name", "sale", "document", "subject", "description",
            "status", "assigned_to", "assigned_to_display", "created_by", "created_by_display",
            "closed_at", "next_appointment_at", "created_at", "updated_at",
        ]
        # next_appointment_at is read-only here on purpose: it changes only
        # through schedule_after_sales_appointment (the schedule-appointment
        # action below), never through a plain create/update, so its own
        # permission rule (elevated, or the assigned technician) cannot be
        # bypassed by writing the field directly on this serializer.
        read_only_fields = ["id", "customer_name", "assigned_to_display", "created_by", "created_by_display", "closed_at", "next_appointment_at", "created_at", "updated_at"]

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
