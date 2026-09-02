from django.db import transaction
from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.access import is_crm_identity
from accounts.models import User
from auditlog.services import log_activity
from common.exceptions import BusinessConflictError, BusinessPermissionDenied
from common.permissions import FeatureGatedAPIMixin
from common.throttles import SensitiveRateThrottle


class StrictQueryParametersMixin(FeatureGatedAPIMixin):
    common_list_query_parameters = {"format", "ordering", "page", "search"}
    list_query_parameters = set()
    action_query_parameters = {}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method not in {"GET", "HEAD"}:
            return
        action_name = getattr(self, "action", None)
        allowed = {"format"} | set(self.action_query_parameters.get(action_name, set()))
        if action_name == "list":
            allowed |= self.common_list_query_parameters | set(self.list_query_parameters)
        errors = {
            name: ["پارامتر نامعتبر است."]
            for name in sorted(set(request.query_params) - allowed)
        }
        for name in sorted(set(request.query_params) & allowed):
            if len(request.query_params.getlist(name)) > 1:
                errors[name] = ["این پارامتر باید فقط یک‌بار وارد شود."]
        if errors:
            raise ValidationError(errors)


class HardDeleteMixin:
    """Real, irreversible deletion of one row, or several — Platform Admin
    only, for correcting a mistaken entry, never a bulk clean-up tool.

    2026-09-02 product-owner decision: every list page gets a checkbox column
    and a Delete action, but only a Platform Admin may ever use it — everyone
    else must ask a Platform Admin, exactly as `accounts.services` already
    requires for user administration. That is enforced here, at the object
    boundary, regardless of what a viewset's own `permission_classes` would
    otherwise allow through for the HTTP method.

    Deletion is safe to hand over at all only because of a pre-existing
    schema property, not new code written for this: every foreign key in this
    project is `on_delete=PROTECT`, with the sole exception of
    `UserCapabilityOverride`'s cascade to its own `User` row (a personal
    setting, not a business record). A row anything else still points to
    therefore cannot be deleted out from under those references — Django
    raises `ProtectedError` before any row is touched, and that is turned
    into an ordinary Persian conflict response instead of an unhandled 500,
    pointing the admin at deactivation instead.

    Every deletion is written to the audit log *before* the row disappears —
    `ActivityLog.object_type`/`object_id` are plain strings captured at write
    time, not a live foreign key, so the record of who deleted what survives
    the row itself.
    """

    def get_throttles(self):
        # Composes with `SensitiveActionThrottleMixin.get_throttles` (whoever
        # is mixed in closer to `object` in the MRO runs first via `super()`)
        # rather than requiring every consuming viewset to remember to list
        # "destroy" and "bulk_delete" in its own `sensitive_actions` — this
        # throttle applies to every viewset that gets real DELETE from this
        # mixin, unconditionally, including one with no `sensitive_actions`
        # of its own (e.g. `InteractionViewSet`).
        throttles = super().get_throttles()
        if getattr(self, "action", None) in {"destroy", "bulk_delete"}:
            throttles.append(SensitiveRateThrottle())
        return throttles

    def _extra_delete_guard(self, request, instance):
        """Hook for a subclass to refuse one specific row beyond the blanket
        Platform-Admin-only gate — e.g. `UserViewSet` refusing self-deletion
        and refusing to ever remove the Platform Admin account through this
        path. A no-op here; raise `BusinessPermissionDenied` to refuse.
        """
        return

    @staticmethod
    def _require_platform_admin(request):
        if not is_crm_identity(request.user) or request.user.role != User.Role.PLATFORM_ADMIN:
            raise BusinessPermissionDenied("حذف رکورد فقط برای مدیر پلتفرم مجاز است.")

    def _delete_instance(self, request, instance):
        self._extra_delete_guard(request, instance)
        with transaction.atomic():
            # Logged first: `instance.delete()` clears the in-memory `.pk`,
            # and the row itself is gone right after — this call is the only
            # remaining place either fact is recorded.
            log_activity(actor=request.user, operation=f"{instance._meta.model_name}.deleted", instance=instance)
            instance.delete()

    def destroy(self, request, *args, **kwargs):
        self._require_platform_admin(request)
        instance = self.get_object()
        try:
            self._delete_instance(request, instance)
        except ProtectedError as exc:
            raise BusinessConflictError(
                {"id": "این رکورد سوابق وابسته دارد و قابل حذف نیست؛ به‌جای حذف، غیرفعال‌سازی را در نظر بگیرید."}
            ) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)

    #: A correction tool for a handful of mistaken rows, not a data-management
    #: bulk operation — capped well below anything a real cleanup job would need.
    MAX_BULK_DELETE = 200

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        self._require_platform_admin(request)
        ids = request.data.get("ids")
        if (
            not isinstance(ids, list)
            or not (1 <= len(ids) <= self.MAX_BULK_DELETE)
            or not all(isinstance(pk, int) and not isinstance(pk, bool) for pk in ids)
        ):
            raise ValidationError({"ids": [f"فهرست شناسه‌های عددی (بین ۱ تا {self.MAX_BULK_DELETE} مورد) لازم است."]})
        # Scoped through the viewset's own `list` queryset — the same rows a
        # bulk-delete request could see are the same rows it can act on.
        found = {obj.pk: obj for obj in self.filter_queryset(self.get_queryset()).filter(pk__in=ids)}
        result = {"deleted": [], "protected": [], "denied": [], "not_found": []}
        for pk in ids:
            instance = found.get(pk)
            if instance is None:
                result["not_found"].append(pk)
                continue
            try:
                self._delete_instance(request, instance)
                result["deleted"].append(pk)
            except ProtectedError:
                result["protected"].append(pk)
            except PermissionDenied:
                # Catches `BusinessPermissionDenied` too (a subclass) — either
                # the blanket gate or a subclass's own `_extra_delete_guard`
                # (e.g. `UserViewSet` refusing self-deletion). One denied row
                # in a batch skips only that row.
                result["denied"].append(pk)
        return Response(result)


class AdminHardDeleteModelViewSet(HardDeleteMixin, StrictQueryParametersMixin, viewsets.ModelViewSet):
    """The ordinary CRUD viewset for this project: list/retrieve/create/update
    for whoever a viewset's own permission classes allow, plus real DELETE —
    single or bulk — for a Platform Admin only, per `HardDeleteMixin` above.

    Formerly `NoDestroyModelViewSet`, when DELETE was refused to everyone;
    renamed with the 2026-09-02 change that gave Platform Admin real deletion,
    since the old name described exactly the opposite of what this now does.
    """

    # No bare PUT, same as before this class could destroy anything — a
    # write is always a partial PATCH in this project. "delete" is the one
    # method added by this change; `HardDeleteMixin.destroy` is what actually
    # gates who may use it.
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
