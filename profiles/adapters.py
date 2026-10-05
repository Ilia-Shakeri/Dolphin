"""The two person types Dolphin has today: a customer and a user.

Each adapter answers the profile page's questions for its type — who is in
scope, what the header says, which tabs and quick actions a viewer gets —
by reading the owning module's own selectors and the viewer's capability set.
Nothing here widens anyone's access: every rule below is either the rule the
old detail page already applied or a narrower one, and each tab's API
enforces it again on its own.
"""

from django.db.models import Q
from django.urls import reverse

from accounts.access import capabilities_for, crm_identities, has_any_capability
from accounts.middleware import is_online
from accounts.models import User, UserAvatar
from common.deployment.profile import feature_enabled
from common.jalali import to_persian_digits
from profiles.registry import PersonAdapter, ProfileTab, QuickAction
from reports.selectors import users_for_performance_report
from sales.selectors import customers_for

#: `User.Role` in Persian, as the rest of the panel says it. Kept in step with
#: `common.ui_views.ROLE_LABELS` by `profiles/tests` rather than imported, so
#: this module does not depend on the page layer.
ROLE_LABELS = {
    User.Role.SALES_AGENT: "بازاریاب (کال سنتر)",
    User.Role.SALES_MANAGER: "مدیر فروشگاه",
    User.Role.COMPANY_IT: "مدیر فنی مشتری",
    User.Role.PLATFORM_ADMIN: "مدیر پلتفرم",
}
WORKSTREAM_LABELS = {
    User.Workstream.SALES: "فروش و تماس‌ها",
    User.Workstream.AFTER_SALES: "خدمات پس از فروش",
}

USER_MANAGE_CAPABILITIES = ("users.manage_agents", "users.manage_non_platform", "users.manage_all")
ROLE_CHANGE_CAPABILITIES = ("users.manage_non_platform", "users.manage_all")


def initials(name):
    """One or two letters for the avatar circle."""
    parts = [part for part in (name or "").split() if part]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return (name or "?")[:2].upper()


def phone_payload(raw, normalized):
    """What the header needs to show and dial a number, or `None`.

    `normalized` is E.164 (`+98912…`); the reader sees it the way people in
    Iran write it (`۰۹۱۲…`), and `tel:` gets the international form so a
    softphone or a mobile browser dials it unchanged. A number that never
    normalised (an internal extension, a foreign number) is still shown and
    still dialled as typed.
    """
    raw = (raw or "").strip()
    if not raw and not normalized:
        return None
    if normalized and normalized.startswith("+98"):
        local = "0" + normalized[3:]
    else:
        local = raw
    dial = normalized or "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    return {
        "display": to_persian_digits(local),
        "e164": normalized or "",
        "tel": f"tel:{dial}" if dial else "",
    }


def _missing(reason):
    """«—» with a tooltip that says why — never an empty slot."""
    return {"value": "", "missing": True, "tooltip": reason}


def _present(value, *, fallback=False, tooltip=""):
    return {"value": value, "missing": False, "fallback": fallback, "tooltip": tooltip}


def managed_users(viewer):
    """The accounts `viewer` may administer — the User Management scope.

    Mirrors `accounts.views.UserViewSet.get_queryset`: only a holder of a
    `users.manage_*` capability has any, a Sales Manager's is the marketers,
    Company IT's is everyone but the Platform Admin.
    """
    if not has_any_capability(viewer, *USER_MANAGE_CAPABILITIES):
        return User.objects.none()
    queryset = crm_identities(User.objects.all())
    if viewer.role == User.Role.SALES_MANAGER:
        queryset = queryset.filter(role=User.Role.SALES_AGENT)
    elif viewer.role == User.Role.COMPANY_IT:
        queryset = queryset.exclude(role=User.Role.PLATFORM_ADMIN)
    return queryset


def _shared_tabs(viewer, capabilities):
    """Tabs every person type has, each behind its own feature and capability."""
    tabs = []
    if feature_enabled("tasks") and capabilities & {"tasks.own", "tasks.company"}:
        tabs.append(ProfileTab("tasks", "وظایف", "di-check-circle", "profiles/tabs/tasks.inc"))
    if feature_enabled("person_notes") and "notes.read" in capabilities:
        tabs.append(ProfileTab("notes", "یادداشت‌ها", "di-notepad", "profiles/tabs/notes.inc", 5))
    return tabs


def _shared_actions(capabilities):
    actions = []
    if feature_enabled("person_notes") and "notes.write" in capabilities:
        actions.append(QuickAction("note", "یادداشت", "di-notepad", tab="notes", icon_paths=5, data={"focus": "profile-note-body"}))
    if feature_enabled("tasks") and "tasks.manage" in capabilities:
        actions.append(QuickAction("task", "وظیفه", "di-add-notepad", action="add-task", icon_paths=4))
    return actions


def call_action(viewer, person_type, person, payload):
    """«تماس»: placed through the PBX from the viewer's own extension when
    they can (telephony, 2.23.0), else the device's own dialler (`tel:`)."""
    if not payload or not payload["tel"]:
        return None
    if feature_enabled("telephony"):
        from telephony.services import can_originate

        if can_originate(viewer):
            return QuickAction(
                "call", "تماس", "di-call", action="originate", primary=True, icon_paths=8,
                data={
                    "number": payload["e164"] or payload["tel"].removeprefix("tel:"),
                    "person-type": person_type,
                    "person-id": str(person.pk),
                },
            )
    return QuickAction("call", "تماس", "di-call", href=payload["tel"], primary=True, icon_paths=8)


def _with_calls(pulled, events):
    """A pull timeline plus the PBX calls telephony found for it."""
    if not events:
        return pulled
    return {"count": pulled["count"] + len(events), "events": [*pulled["events"], *events]}


def merged_timeline(viewer, person_type, person, pulled):
    """The pull sources plus what was recorded here (`timeline.TimelineEntry`),
    newest first, in one list."""
    from common.customer_timeline import TIMELINE_LIMIT
    from timeline.selectors import recorded_events_for

    count, recorded = recorded_events_for(viewer, person_type, person.pk, limit=TIMELINE_LIMIT)
    events = [*pulled["events"], *recorded]
    events.sort(key=lambda event: (event["at"] is not None, event["at"] or ""), reverse=True)
    return {"count": pulled["count"] + count, "events": events[:TIMELINE_LIMIT]}


def performance_scope(viewer):
    """Whose performance `viewer` may read — `users_for_performance_report`,
    and only where this deployment runs reports and the viewer holds one of
    the two report capabilities the report API itself requires."""
    if not feature_enabled("reports") or not has_any_capability(viewer, "reports.own", "reports.company"):
        return User.objects.none()
    return users_for_performance_report(viewer)


class CustomerAdapter(PersonAdapter):
    key = "customer"
    label = "مشتری"
    required_feature = "customers"

    def scoped_queryset(self, viewer):
        return customers_for(viewer).select_related("created_by").prefetch_related("phones")

    def display_name(self, person):
        return person.full_name

    def profile_url(self, person):
        return reverse("common_ui:customer-detail", args=[person.pk])

    def primary_phone(self, person):
        phones = [phone for phone in person.phones.all() if phone.is_active]
        phones.sort(key=lambda phone: (not phone.is_primary, phone.pk))
        return phones[0] if phones else None

    def header(self, viewer, person):
        phone = self.primary_phone(person)
        job_title = (
            _present(person.job_title)
            if person.job_title
            else _present(
                f"مشتری {person.get_kind_display()}",
                fallback=True,
                tooltip="سمتی برای این مشتری ثبت نشده است؛ نوع مشتری نشان داده می‌شود.",
            )
        )
        return {
            "type": self.key,
            "type_label": self.label,
            "id": person.pk,
            "name": person.full_name,
            "initials": initials(person.full_name),
            "avatar_url": "",
            "badge": None if person.is_active else {"label": "غیرفعال", "accent": "danger"},
            "presence": None,
            "job_title": job_title,
            "province": (
                _present(person.province)
                if person.province
                else _missing("استان این مشتری ثبت نشده است.")
            ),
            "phone": (
                phone_payload(phone.raw_phone, phone.normalized_phone)
                if phone
                else None
            ),
            "phone_missing_tooltip": "تلفن فعالی برای این مشتری ثبت نشده است.",
            "email": person.email,
        }

    def tabs(self, viewer, person):
        capabilities = capabilities_for(viewer)
        tabs = [
            ProfileTab("overview", "بررسی اجمالی", "di-element-11", "profiles/tabs/customer_overview.inc", 4),
            ProfileTab("info", "اطلاعات", "di-profile-circle", "profiles/tabs/customer_info.inc", 3),
        ]
        if feature_enabled("leads") and capabilities.intersection({"leads.scoped", "leads.company"}):
            tabs.append(ProfileTab("leads", "سرنخ‌ها", "di-rocket", "profiles/tabs/customer_leads.inc"))
        # No «فعالیت‌ها» tab for a customer (2.27.0, product owner): the
        # overview's «آخرین رویدادها» box now holds the whole timeline,
        # scrollable, so a second tab repeating it only split one list in two.
        sees_logged_calls = feature_enabled("leads") and capabilities.intersection({"interactions.scoped", "interactions.company"})
        # Since 2.27.0 a customer's calls tab is the call-centre records only
        # (the PBX box left it), so it exists exactly when those can be read.
        if sees_logged_calls:
            tabs.append(ProfileTab("calls", "تماس‌ها", "di-call", "profiles/tabs/customer_calls.inc", 8))
        if feature_enabled("invoices") and capabilities.intersection({"invoices.scoped", "invoices.company"}):
            tabs.append(ProfileTab("finance", "خریدها و مالی", "di-dollar", "profiles/tabs/customer_finance.inc", 3))
        tabs.extend(_shared_tabs(viewer, capabilities))
        if feature_enabled("attachments"):
            tabs.append(ProfileTab("documents", "اسناد", "di-file", "profiles/tabs/documents.inc"))
        if feature_enabled("invoices") and capabilities.intersection({"invoices.scoped", "invoices.company"}):
            tabs.append(ProfileTab("analysis", "تحلیل", "di-chart-simple", "profiles/tabs/customer_analysis.inc", 4))
        return tabs

    def quick_actions(self, viewer, person):
        capabilities = capabilities_for(viewer)
        actions = []
        phone = self.primary_phone(person)
        if phone:
            action = call_action(viewer, self.key, person, phone_payload(phone.raw_phone, phone.normalized_phone))
            if action:
                actions.append(action)
        if feature_enabled("outbound_sms") and "sms.company" in capabilities and phone:
            actions.append(QuickAction("sms", "پیامک", "di-sms", href=f"{reverse('common_ui:outbound-sms')}?customer={person.pk}"))
        if "customers.manage" in capabilities:
            actions.append(QuickAction("edit", "ویرایش", "di-pencil", tab="info"))
        actions.extend(_shared_actions(capabilities))
        if (
            feature_enabled("customer_ledger")
            and capabilities.intersection({"ledger.company", "ledger.own"})
        ):
            actions.append(QuickAction(
                "ledger", "دفتر حساب مشتری", "di-book", in_menu=True, icon_paths=4,
                href=f"{reverse('common_ui:customer-ledger')}?customer={person.pk}",
            ))
        actions.append(QuickAction(
            "back", "بازگشت به فهرست مشتریان", "di-arrow-right", in_menu=True,
            href=reverse("common_ui:customers"),
        ))
        return actions

    def timeline(self, viewer, person):
        from common import customer_timeline

        if not feature_enabled("customer_timeline"):
            return {"count": 0, "events": []}
        pulled = customer_timeline.timeline_for(viewer, person)
        if feature_enabled("telephony"):
            from telephony.profile import customer_call_events

            pulled = _with_calls(pulled, customer_call_events(viewer, person))
        return merged_timeline(viewer, self.key, person, pulled)


class UserAdapter(PersonAdapter):
    key = "user"
    label = "کاربر"

    def scoped_queryset(self, viewer):
        """Whom `viewer` may see a profile of.

        The union of three scopes that each existed before this page: the
        accounts they administer (the old «جزئیات کاربر»), the people whose
        performance they may read (the old «پروفایل»), and themselves.
        """
        return crm_identities(User.objects.all()).filter(
            Q(pk=viewer.pk)
            | Q(pk__in=managed_users(viewer).values("pk"))
            | Q(pk__in=performance_scope(viewer).values("pk"))
        )

    def display_name(self, person):
        return person.get_full_name() or person.username

    def profile_url(self, person):
        return reverse("common_ui:user-detail", args=[person.pk])

    def manages(self, viewer, person):
        return managed_users(viewer).filter(pk=person.pk).exists()

    def reads_performance(self, viewer, person):
        return performance_scope(viewer).filter(pk=person.pk).exists()

    def header(self, viewer, person):
        name = self.display_name(person)
        role_label = ROLE_LABELS.get(person.role, person.role)
        if person.role == User.Role.SALES_AGENT and person.workstream == User.Workstream.AFTER_SALES:
            role_label = f"{role_label} — خدمات پس از فروش"
        has_photo = UserAvatar.objects.filter(pk=person.pk).exists()
        if has_photo:
            avatar_url = f"/api/v1/users/{person.pk}/avatar/image/"
        else:
            from accounts.avatars import default_avatar_url

            avatar_url = default_avatar_url(person) or ""
        online = is_online(person)
        return {
            "type": self.key,
            "type_label": self.label,
            "id": person.pk,
            "name": name,
            "initials": initials(name),
            "avatar_url": avatar_url,
            "badge": (
                {"label": "فعال", "accent": "success"}
                if person.is_active
                else {"label": "غیرفعال", "accent": "danger"}
            ),
            "presence": {
                "online": online,
                "last_seen_at": person.last_seen_at,
                "label": "آنلاین" if online else "",
            },
            "job_title": (
                _present(person.job_title)
                if person.job_title
                else _present(role_label, fallback=True, tooltip="سمتی ثبت نشده است؛ نقش کاربر نشان داده می‌شود.")
            ),
            "role_label": role_label,
            "province": (
                _present(person.province)
                if person.province
                else _missing("استان این کاربر ثبت نشده است.")
            ),
            "phone": phone_payload(person.phone, person.normalized_phone),
            "phone_missing_tooltip": "تلفنی برای این کاربر ثبت نشده است.",
            "email": person.email,
            "username": person.username,
        }

    def tabs(self, viewer, person):
        capabilities = capabilities_for(viewer)
        manages = self.manages(viewer, person)
        own = person.pk == viewer.pk
        tabs = [ProfileTab("overview", "بررسی اجمالی", "di-element-11", "profiles/tabs/user_overview.inc", 4)]
        if manages or own:
            tabs.append(ProfileTab("info", "اطلاعات", "di-profile-circle", "profiles/tabs/user_info.inc", 3))
        if feature_enabled("leads") and capabilities.intersection({"leads.scoped", "leads.company"}):
            tabs.append(ProfileTab("leads", "مشتریان و سرنخ‌ها", "di-rocket", "profiles/tabs/user_leads.inc"))
        if self.reads_performance(viewer, person):
            tabs.append(ProfileTab("performance", "عملکرد", "di-chart-simple", "profiles/tabs/user_performance.inc", 4))
        if feature_enabled("telephony"):
            from telephony.profile import sees_calls_of

            if sees_calls_of(viewer, person):
                tabs.append(ProfileTab("calls", "تماس‌ها", "di-call", "profiles/tabs/user_calls.inc", 8))
        tabs.append(ProfileTab("activity", "فعالیت‌ها", "di-time", "profiles/tabs/activity.inc"))
        tabs.extend(_shared_tabs(viewer, capabilities))
        if manages:
            tabs.append(ProfileTab("access", "دسترسی‌ها", "di-shield-tick", "profiles/tabs/user_access.inc"))
        return tabs

    def quick_actions(self, viewer, person):
        capabilities = capabilities_for(viewer)
        manages = self.manages(viewer, person)
        actions = []
        action = call_action(viewer, self.key, person, phone_payload(person.phone, person.normalized_phone))
        if action:
            actions.append(action)
        if feature_enabled("outbound_sms") and "sms.company" in capabilities and person.normalized_phone:
            actions.append(QuickAction(
                "sms", "پیامک", "di-sms",
                href=f"{reverse('common_ui:outbound-sms')}?phone={person.normalized_phone}",
            ))
        if manages or person.pk == viewer.pk:
            actions.append(QuickAction("edit", "ویرایش", "di-pencil", tab="info"))
        actions.extend(_shared_actions(capabilities))
        if manages and has_any_capability(viewer, *ROLE_CHANGE_CAPABILITIES):
            actions.append(QuickAction(
                "permissions", "مجوزها", "di-key", action="permissions", in_menu=True,
                data={"user-id": str(person.pk), "user-name": self.display_name(person)},
            ))
            actions.append(QuickAction("sessions", "نشست‌های فعال", "di-lock", tab="access", in_menu=True, icon_paths=3))
        if manages:
            actions.append(QuickAction(
                "back", "بازگشت به فهرست کاربران", "di-arrow-right", in_menu=True,
                href=reverse("common_ui:users"),
            ))
        return actions

    def timeline(self, viewer, person):
        from profiles import user_timeline

        pulled = user_timeline.timeline_for(viewer, person)
        if feature_enabled("telephony"):
            from telephony.profile import user_call_events

            pulled = _with_calls(pulled, user_call_events(viewer, person))
        return merged_timeline(viewer, self.key, person, pulled)
