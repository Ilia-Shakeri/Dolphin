"""Saved list views (2.40.54, feature `customization`).

Owner decision 2026-10-14 (Q18): «نماهای ذخیره‌شدهٔ جدول، شخصی یا تیمی». A
person saves a list page's filters under a name and applies them again with
one choice. A view is personal; sharing it with everyone who opens that page
needs `views.share` (a store manager and the Platform Admin by default, one row
in the permission matrix). A view only refills the page's own filter form: the
list it brings back is whatever that page's own scope already allows the
reader, so a shared view can never show anyone more than they could filter for
by hand.
"""

import re

from django.db import transaction
from django.db.models import Q

from accounts.access import has_any_capability
from auditlog.services import log_activity
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from customization.models import MAX_VIEWS_PER_PAGE, VIEW_NAME_MAX_LENGTH, SavedView
from customization.services import enabled

SHARE_CAPABILITY = "views.share"
PAGE_SHAPE = re.compile(r"\A[a-z0-9-]{1,40}:[a-z0-9-]{1,60}\Z")
FIELD_SHAPE = re.compile(r"\A[A-Za-z0-9_-]{1,80}\Z")
MAX_FIELDS = 40
VALUE_MAX_LENGTH = 300


def can_share(user):
    return has_any_capability(user, SHARE_CAPABILITY)


def _clean_page(page):
    page = str(page or "")
    if not PAGE_SHAPE.fullmatch(page):
        raise BusinessRuleError({"page": "صفحهٔ این نما شناخته نشد."})
    return page


def _clean_state(state):
    if not isinstance(state, dict) or len(state) > MAX_FIELDS:
        raise BusinessRuleError({"state": "فیلترهای این نما خوانده نشد."})
    cleaned = {}
    for key, value in state.items():
        if not FIELD_SHAPE.fullmatch(str(key)):
            raise BusinessRuleError({"state": "فیلترهای این نما خوانده نشد."})
        if isinstance(value, bool):
            value = "true" if value else "false"
        text = str(value if value is not None else "")
        if len(text) > VALUE_MAX_LENGTH:
            raise BusinessRuleError({"state": "مقدار یکی از فیلترها بیش از اندازه بلند است."})
        cleaned[str(key)] = text
    return cleaned


def views_for(user, page):
    """The reader's own views of this page, then those others shared."""
    if not enabled():
        return []
    page = _clean_page(page)
    return list(
        SavedView.objects.filter(page=page).filter(Q(owner=user) | Q(shared=True))
        .select_related("owner").order_by("-shared", "name", "id")
    )


def serialize(view, user):
    return {
        "id": view.pk, "name": view.name, "shared": view.shared, "state": view.state,
        "mine": view.owner_id == user.pk,
        "owner_display": view.owner.get_full_name() or view.owner.username,
    }


@transaction.atomic
def save_view(*, actor, page, name, state, shared=False):
    """Save (or overwrite one of the actor's own of the same name)."""
    if not enabled():
        raise BusinessRuleError({"page": "شخصی‌سازی در این استقرار فعال نیست."})
    page = _clean_page(page)
    name = " ".join(str(name or "").split())
    if not name:
        raise BusinessRuleError({"name": "نامی برای این نما بنویسید."})
    if len(name) > VIEW_NAME_MAX_LENGTH:
        raise BusinessRuleError({"name": f"نام نما نباید بیش از {VIEW_NAME_MAX_LENGTH} نویسه باشد."})
    if shared and not can_share(actor):
        raise BusinessPermissionDenied("اشتراک نما با تیم مجاز نیست.")
    state = _clean_state(state)
    existing = SavedView.objects.select_for_update().filter(owner=actor, page=page, name=name).first()
    if existing is None:
        if SavedView.objects.filter(owner=actor, page=page).count() >= MAX_VIEWS_PER_PAGE:
            raise BusinessRuleError({"name": f"هر صفحه حداکثر {MAX_VIEWS_PER_PAGE} نمای ذخیره‌شده دارد."})
        view = SavedView.objects.create(owner=actor, page=page, name=name, state=state, shared=bool(shared))
        operation = "saved_view.created"
    else:
        existing.state = state
        existing.shared = bool(shared)
        existing.save(update_fields=["state", "shared", "updated_at"])
        view = existing
        operation = "saved_view.updated"
    if shared:
        log_activity(actor=actor, operation=operation, instance=view, changes={"fields": ["name", "state", "shared"]})
    return view


@transaction.atomic
def delete_view(*, actor, view):
    """One's own view; a shared one may also be removed by whoever may share."""
    locked = SavedView.objects.select_for_update().get(pk=view.pk)
    if locked.owner_id != actor.pk and not (locked.shared and can_share(actor)):
        raise BusinessPermissionDenied("این نما متعلق به شما نیست.")
    if locked.shared:
        log_activity(actor=actor, operation="saved_view.deleted", instance=locked, changes={"fields": ["name"]})
    locked.delete()
