"""`/api/v1/tasks/` — list, create and move tasks (2.20.0).

Feature `tasks`; reading needs `tasks.own` or `tasks.company`, writing also
`tasks.manage`, permanent deletion `tasks.delete` (or the Platform Admin).
Scope is `tasks.selectors.tasks_for`; every rule is re-checked by the
services in `tasks/services.py`.
"""

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.access import crm_identities
from accounts.models import User
from common.openapi import ACCESS_DENIED_RESPONSE, CONFLICT_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import HasCapabilityForMethod, IsActiveAuthenticated
from common.serializers import RejectServerFieldsMixin
from common.throttles import SensitiveActionThrottleMixin
from common.viewsets import AdminHardDeleteModelViewSet
from tasks.models import TASK_NOTES_MAX_LENGTH, TASK_TITLE_MAX_LENGTH, Task
from tasks.selectors import tasks_for
from tasks.services import cancel_task, complete_task, create_task, reopen_task, update_task

#: Where a task about a person links to.
PERSON_URLS = {"customer": "/customers/{}/", "user": "/users/{}/"}


class TaskSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {
        "assignee_display", "status", "status_display", "completed_at", "source", "person_url",
        "overdue", "created_by", "created_by_display", "created_at", "updated_at",
    }
    title = serializers.CharField(max_length=TASK_TITLE_MAX_LENGTH)
    notes = serializers.CharField(max_length=TASK_NOTES_MAX_LENGTH, required=False, allow_blank=True)
    assignee = serializers.PrimaryKeyRelatedField(queryset=User.objects.none(), required=False)
    person_type = serializers.CharField(max_length=32, required=False, allow_blank=True)
    person_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    assignee_display = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    person_url = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()
    created_by_display = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            "id", "title", "notes", "due_at", "assignee", "assignee_display", "person_type", "person_id",
            "person_url", "status", "status_display", "completed_at", "source", "overdue", "created_by",
            "created_by_display", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "assignee_display", "person_url", "status", "status_display", "completed_at", "source",
            "overdue", "created_by", "created_by_display", "created_at", "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Any active colleague is a *candidate*; whether this actor may hand
        # them a task is `tasks.services._check_assignee`'s decision.
        self.fields["assignee"].queryset = crm_identities(User.objects.filter(is_active=True))

    def get_assignee_display(self, task) -> str:
        return task.assignee.get_full_name() or task.assignee.username

    def get_created_by_display(self, task) -> str:
        if task.created_by_id is None:
            return "سامانه"
        return task.created_by.get_full_name() or task.created_by.username

    def get_person_url(self, task) -> str:
        pattern = PERSON_URLS.get(task.person_type)
        return pattern.format(task.person_id) if pattern and task.person_id else ""

    def get_overdue(self, task) -> bool:
        return bool(task.status == Task.Status.OPEN and task.due_at and task.due_at < timezone.now())

    def create(self, validated_data):
        actor = self.context["request"].user
        return create_task(
            actor=actor,
            title=validated_data["title"],
            notes=validated_data.get("notes", ""),
            due_at=validated_data.get("due_at"),
            assignee=validated_data.get("assignee") or actor,
            person_type=validated_data.get("person_type", "") or "",
            person_id=validated_data.get("person_id"),
        )

    def update(self, instance, validated_data):
        for field in ("person_type", "person_id"):
            if field in validated_data:
                raise ValidationError({field: "شخص مرتبط یک وظیفه پس از ثبت تغییر نمی‌کند."})
        return update_task(actor=self.context["request"].user, task=instance, **validated_data)


class HasTaskCapability(HasCapabilityForMethod):
    pass


class TaskViewSet(SensitiveActionThrottleMixin, AdminHardDeleteModelViewSet):
    required_feature = "tasks"
    required_capabilities = ("tasks.own", "tasks.company")
    required_write_capabilities = ("tasks.manage",)
    delete_capability = "tasks.delete"
    permission_classes = [IsActiveAuthenticated, HasTaskCapability]
    serializer_class = TaskSerializer
    queryset = Task.objects.none()
    sensitive_actions = frozenset({"create", "partial_update", "complete", "cancel", "reopen"})
    search_fields = ["title", "notes"]
    ordering_fields = ["due_at", "created_at", "status"]
    list_query_parameters = {"status", "assignee", "person_type", "person_id", "due_before"}

    def get_queryset(self):
        queryset = tasks_for(self.request.user).select_related("assignee", "created_by")
        if self.action != "list":
            return queryset
        params = self.request.query_params
        status_value = params.get("status")
        if status_value:
            if status_value not in Task.Status.values:
                raise ValidationError({"status": "وضعیت وظیفه نامعتبر است."})
            queryset = queryset.filter(status=status_value)
        for name in ("assignee", "person_id"):
            value = params.get(name)
            if value:
                if not value.isdigit():
                    raise ValidationError({name: "شناسه باید عدد باشد."})
                queryset = queryset.filter(**{f"{name}_id" if name == "assignee" else name: int(value)})
        person_type = params.get("person_type")
        if person_type:
            queryset = queryset.filter(person_type=person_type)
        due_before = params.get("due_before")
        if due_before:
            parsed = serializers.DateTimeField().to_internal_value(due_before)
            queryset = queryset.filter(due_at__lt=parsed)
        # Open first, soonest due first, undated open tasks after dated ones.
        return queryset.order_by("status", "due_at", "id")

    @extend_schema(parameters=[
        OpenApiParameter("status", str, description="`open`, `done` or `cancelled`."),
        OpenApiParameter("assignee", int, description="Tasks assigned to this user id (within the caller's scope)."),
        OpenApiParameter("person_type", str, description="`customer` or `user` — tasks about that person type."),
        OpenApiParameter("person_id", int, description="Tasks about this person id."),
        OpenApiParameter("due_before", str, description="Exclusive ISO 8601 instant on `due_at`."),
    ])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def _transition(self, service):
        task = service(actor=self.request.user, task=self.get_object())
        return Response(self.get_serializer(task).data)

    @extend_schema(request=None, responses={200: TaskSerializer, 403: ACCESS_DENIED_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE})
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._transition(complete_task)

    @extend_schema(request=None, responses={200: TaskSerializer, 403: ACCESS_DENIED_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._transition(cancel_task)

    @extend_schema(request=None, responses={200: TaskSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE})
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._transition(reopen_task)
