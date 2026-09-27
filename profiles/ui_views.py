"""The person profile page — one template for every kind of person (2.19.0).

`/customers/<id>/` and `/users/<id>/` both render `profiles/profile.html`; the
adapter registered for the type decides what is on it. The header is rendered
here, from data this view already holds after its scope check; each tab's
*data* is fetched by the page only when that tab is first opened, so a
profile with eight tabs costs one query set up front, not eight.

The two older addresses of the user profile, `/users/<id>/profile/` and
`/profile/`, redirect here with `?tab=performance`, so every bookmark and
every link already in the panel lands on the same page.
"""

from django.shortcuts import redirect
from django.urls import reverse

from accounts.access import assignable_roles, capabilities_for, crm_identities, has_any_capability
from accounts.models import User
from common.deployment.profile import feature_enabled
from common.provinces import province_names
from common.ui_views import ActiveCrmView
from profiles.adapters import ROLE_CHANGE_CAPABILITIES, WORKSTREAM_LABELS
from profiles.cards import DEFAULT_PERIOD, PERIODS, cards_for
from profiles.completion import completion_for
from profiles.registry import adapter_for


def task_assignees(viewer):
    """Whom `viewer` may give a task: anyone active with `tasks.company`,
    else only themselves (`tasks.services._check_assignee` decides again)."""
    if "tasks.company" not in capabilities_for(viewer):
        return [(viewer.pk, viewer.get_full_name() or viewer.username)]
    people = crm_identities(User.objects.filter(is_active=True)).order_by("first_name", "last_name", "username")
    return [(person.pk, person.get_full_name() or person.username) for person in people]


class PersonProfileView(ActiveCrmView):
    template_name = "profiles/profile.html"
    person_type = ""
    person_id_kwarg = ""
    not_found_title = "پیدا نشد"
    not_found_message = "این مورد در محدوده دسترسی شما وجود ندارد."

    @property
    def adapter(self):
        return adapter_for(self.person_type)

    def get(self, request, *args, **kwargs):
        adapter = self.adapter
        if not adapter.may_open_any(request.user):
            return self.render_to_response(
                self.get_context_data(
                    error_status=403,
                    error_title="دسترسی مجاز نیست",
                    error_message="شما اجازه مشاهده این پروفایل را ندارید.",
                ),
                status=403,
            )
        self.person = adapter.resolve(request.user, kwargs[self.person_id_kwarg])
        if self.person is None:
            # Not 403: someone outside the viewer's scope must not be
            # confirmed to exist.
            return self.render_to_response(
                self.get_context_data(
                    error_status=404,
                    error_title=self.not_found_title,
                    error_message=self.not_found_message,
                ),
                status=404,
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = getattr(self, "person", None)
        if person is None:
            return context
        adapter = self.adapter
        viewer = self.request.user
        tabs = adapter.tabs(viewer, person)
        requested = self.request.GET.get("tab", "")
        keys = [tab.key for tab in tabs]
        actions = adapter.quick_actions(viewer, person)
        context.update(
            person=adapter.header(viewer, person),
            person_object=person,
            profile_tabs=tabs,
            # An unknown or withheld `?tab=` opens the first tab rather than
            # an error: a link from someone with more access than the reader
            # must still land somewhere sensible.
            active_tab=requested if requested in keys else keys[0],
            quick_actions=[action for action in actions if not action.in_menu],
            menu_actions=[action for action in actions if action.in_menu],
            profile_url=adapter.profile_url(person),
            province_names=province_names(),
            # Only the cards this reader may see get a shell; their values
            # arrive from `/api/v1/profiles/<type>/<id>/cards/` (2.20.0).
            stat_cards=cards_for(viewer, adapter.key, person),
            card_periods=PERIODS,
            default_card_period=DEFAULT_PERIOD,
            completion=completion_for(adapter.key, person, can_edit="info" in keys),
        )
        capabilities = capabilities_for(viewer)
        context["can_add_task"] = feature_enabled("tasks") and "tasks.manage" in capabilities
        context["can_write_notes"] = feature_enabled("person_notes") and "notes.write" in capabilities
        if context["can_add_task"]:
            context["task_assignees"] = task_assignees(viewer)
            # A task on a colleague's profile is theirs by default; on a
            # customer's, the reader's own.
            default = person.pk if adapter.key == "user" else viewer.pk
            known = {pk for pk, _ in context["task_assignees"]}
            context["default_task_assignee"] = default if default in known else viewer.pk
        return context


class CustomerProfileView(PersonProfileView):
    required_feature = "customers"
    person_type = "customer"
    person_id_kwarg = "customer_id"
    not_found_title = "مشتری پیدا نشد"
    not_found_message = "مشتری در محدوده دسترسی شما وجود ندارد."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["customer_id"] = self.kwargs[self.person_id_kwarg]
        return context


class UserProfileView(PersonProfileView):
    person_type = "user"
    person_id_kwarg = "user_id"
    not_found_title = "کاربر پیدا نشد"
    not_found_message = "کاربر در محدوده دسترسی شما وجود ندارد."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["target_user_id"] = self.kwargs[self.person_id_kwarg]
        person = getattr(self, "person", None)
        if person is None:
            return context
        viewer = self.request.user
        manages = self.adapter.manages(viewer, person)
        context["is_own_profile"] = person.pk == viewer.pk
        # Which door the «اطلاعات» form saves through: an administrator
        # edits the account (`/api/v1/users/<id>/`, which can also rename
        # it and move its workstream); anyone else only their own profile
        # fields (`/api/v1/auth/me/`). Both services re-check who may.
        context["profile_edit_mode"] = "admin" if manages else ("self" if person.pk == viewer.pk else "")
        context["profile_can_change_roles"] = manages and has_any_capability(viewer, *ROLE_CHANGE_CAPABILITIES)
        context["assignable_roles"] = assignable_roles(viewer) if context["profile_can_change_roles"] else []
        context["workstream_labels"] = WORKSTREAM_LABELS
        context["target_username"] = person.username
        return context


class LegacyUserProfileRedirectView(ActiveCrmView):
    """`/users/<id>/profile/` — the performance page before 2.19.0."""

    def get(self, request, *args, **kwargs):
        return redirect(f"{reverse('common_ui:user-detail', args=[kwargs['user_id']])}?tab=performance")


class MyProfileRedirectView(ActiveCrmView):
    """`/profile/` — "my own profile", with no id to look up first."""

    def get(self, request, *args, **kwargs):
        return redirect(f"{reverse('common_ui:user-detail', args=[request.user.pk])}?tab=performance")
