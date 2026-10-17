"""Call outcomes and the do-not-contact list (2.40.58, BIZ-003).

Product owner, 2026-10-17:

* an outcome is chosen from a list, for every call, with free text beside it;
  the twelve standard outcomes are «پاسخ نداد، خط اشغال بود، شماره اشتباه یا
  نامعتبر، تماس برقرار شد، علاقه‌مند، نیازمند پیگیری، درخواست پیش‌فاکتور، خرید
  انجام شد، عدم تمایل به خرید، تماس در زمان دیگری، عدم تماس مجدد، سایر»;
* a *successful* call is one where someone was really reached — not «پاسخ
  نداد», «خط اشغال» or «شماره نامعتبر»;
* *qualified* is a separate option, possible only on «علاقه‌مند»، «نیازمند
  پیگیری» and «درخواست پیش‌فاکتور», when a real need was confirmed;
* «نیازمند پیگیری» needs the next follow-up's date and time;
* «عدم تماس مجدد» takes the number out of marketing calls and new campaigns,
  keeping everything already recorded;
* «خرید انجام شد» is not a sale — a sale is a valid invoice;
* calls, successful calls, qualified calls and sales are counted apart;
* older calls keep their words and are matched to the list by hand, or
  automatically only when certain;
* a company may add its own outcomes; the standard ones stay for reporting.

Three controls: recording a call is the `leads` feature and the record's own
permission; adding a company outcome needs `customization` and
`customization.manage`; matching older calls and lifting a do-not-contact
need `customization.manage` (a manager-side correction) without the feature.
"""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from accounts.access import has_any_capability
from accounts.models import User
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from common.phones import normalized_or_blank
from sales.customer_backfill import clean_label, normalize_label
from sales.models import PIPELINE_LABEL_MAX_LENGTH, STAGE_REASON_MAX_LENGTH, CallOutcome, DoNotContact, Interaction

CAPABILITY = "customization.manage"
FEATURE = "customization"
MAX_COMPANY_OUTCOMES = 30


@dataclass(frozen=True)
class Standard:
    key: str
    label: str
    #: Someone was really reached.
    contact: bool
    may_qualify: bool = False
    needs_follow_up: bool = False
    stops_contact: bool = False


STANDARD = {item.key: item for item in (
    Standard("no_answer", "پاسخ نداد", contact=False),
    Standard("busy", "خط اشغال بود", contact=False),
    Standard("wrong_number", "شماره اشتباه یا نامعتبر", contact=False),
    Standard("connected", "تماس برقرار شد", contact=True),
    Standard("interested", "علاقه‌مند", contact=True, may_qualify=True),
    Standard("needs_follow_up", "نیازمند پیگیری", contact=True, may_qualify=True, needs_follow_up=True),
    Standard("quote_requested", "درخواست پیش‌فاکتور", contact=True, may_qualify=True),
    Standard("purchased", "خرید انجام شد", contact=True),
    Standard("not_interested", "عدم تمایل به خرید", contact=True),
    Standard("call_later", "تماس در زمان دیگری", contact=True),
    Standard("do_not_call", "عدم تماس مجدد", contact=True, stops_contact=True),
    Standard("other", "سایر", contact=True),
)}
SUCCESSFUL = frozenset(key for key, item in STANDARD.items() if item.contact)
MAY_QUALIFY = frozenset(key for key, item in STANDARD.items() if item.may_qualify)


# --- the list --------------------------------------------------------------------


def ensure_defaults():
    """The standard outcomes, put back if the table was emptied."""
    if CallOutcome.objects.filter(is_system=True).count() == len(STANDARD):
        return
    for position, item in enumerate(STANDARD.values(), start=1):
        CallOutcome.objects.get_or_create(
            key=item.key,
            defaults={"label": item.label, "standard_key": item.key, "position": position, "is_system": True},
        )


def outcomes(*, active_only=False):
    ensure_defaults()
    queryset = CallOutcome.objects.all()
    if active_only:
        queryset = queryset.filter(is_active=True)
    return list(queryset.order_by("position", "id"))


def serialize_outcome(outcome):
    standard = STANDARD[outcome.standard_key]
    return {
        "id": outcome.pk, "key": outcome.key, "label": outcome.label, "standard_key": outcome.standard_key,
        "standard_label": standard.label, "successful": standard.contact, "may_qualify": standard.may_qualify,
        "needs_follow_up": standard.needs_follow_up, "stops_contact": standard.stops_contact,
        "position": outcome.position, "is_system": outcome.is_system, "is_active": outcome.is_active,
    }


def outcomes_payload():
    """What a call form embeds, and the settings card reads."""
    return {
        "outcomes": [serialize_outcome(outcome) for outcome in outcomes()],
        "standards": [{"key": item.key, "label": item.label} for item in STANDARD.values()],
    }


def label_for(key):
    outcome = CallOutcome.objects.filter(key=key).first()
    return outcome.label if outcome else key


# --- one call --------------------------------------------------------------------


def clean_call(data):
    """Check a call's outcome against the rules and fill what follows from it.

    `data` is the call being recorded; `result` (a key) is required, `qualified`
    allowed only where the standard outcome may qualify, and «نیازمند پیگیری»
    needs `next_follow_up_at`. `outcome` — the call's own words since before
    the list — becomes the outcome's name when nothing else is written.
    Returns the outcome's `Standard`.
    """
    key = str(data.get("result") or "").strip()
    if not key:
        raise BusinessRuleError({"result": "نتیجهٔ تماس را از فهرست انتخاب کنید."})
    outcome = next((item for item in outcomes(active_only=True) if item.key == key), None)
    if outcome is None:
        raise BusinessRuleError({"result": "این نتیجه در فهرست نیست یا خاموش است."})
    standard = STANDARD[outcome.standard_key]
    qualified = bool(data.get("qualified"))
    if qualified and not standard.may_qualify:
        raise BusinessRuleError({"qualified": "«واجد شرایط» فقط برای علاقه‌مند، نیازمند پیگیری و درخواست پیش‌فاکتور است."})
    if standard.needs_follow_up and not data.get("next_follow_up_at"):
        raise BusinessRuleError({"next_follow_up_at": "برای «نیازمند پیگیری»، تاریخ و ساعت پیگیری بعدی را بنویسید."})
    data["result"] = outcome.key
    data["result_standard"] = standard.key
    data["qualified"] = qualified
    if not str(data.get("outcome") or "").strip():
        data["outcome"] = outcome.label
    return standard


def after_call(interaction, standard, actor):
    """What a recorded call sets off: «عدم تماس مجدد» adds its number."""
    if standard.stops_contact:
        block_number(actor=actor, phone=interaction.normalized_phone, interaction=interaction, note=interaction.notes[:300])


# --- do not contact --------------------------------------------------------------


def blocked_numbers(phones):
    """Which of these (E.164) numbers are on the list now."""
    phones = [phone for phone in phones if phone]
    if not phones:
        return set()
    return set(
        DoNotContact.objects.filter(normalized_phone__in=phones, lifted_at__isnull=True)
        .values_list("normalized_phone", flat=True)
    )


def is_blocked(phone):
    """Whether this number — as written or in E.164 — is on the list now."""
    normalized = phone if str(phone or "").startswith("+98") else normalized_or_blank(phone)
    return bool(normalized) and DoNotContact.objects.filter(normalized_phone=normalized, lifted_at__isnull=True).exists()


def block_number(*, actor, phone, interaction=None, note=""):
    """Put a number on the list; a number already on it stays as it is."""
    if not phone or DoNotContact.objects.filter(normalized_phone=phone, lifted_at__isnull=True).exists():
        return None
    row = DoNotContact.objects.create(normalized_phone=phone, interaction=interaction, note=note, created_by=actor)
    log_activity(actor=actor, operation="do_not_contact.added", instance=row, changes={"interaction": getattr(interaction, "pk", None)})
    return row


@transaction.atomic
def lift_block(*, actor, row, reason):
    """Take a number off the list, with a reason; the row stays as history."""
    from sales.services import ELEVATED_OPERATORS, _lock_active_actor

    actor = _lock_active_actor(actor)
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("برداشتن شماره از فهرست «عدم تماس مجدد» کار مدیر است.")
    reason = " ".join(str(reason or "").split())
    if not reason:
        raise BusinessRuleError({"reason": "دلیل را بنویسید."})
    if len(reason) > STAGE_REASON_MAX_LENGTH:
        raise BusinessRuleError({"reason": f"دلیل نباید بیش از {STAGE_REASON_MAX_LENGTH} نویسه باشد."})
    locked = DoNotContact.objects.select_for_update().get(pk=row.pk)
    if locked.lifted_at is not None:
        raise BusinessConflictError({"reason": "این شماره پیش‌تر از فهرست برداشته شده است."})
    locked.lifted_at, locked.lifted_by, locked.lift_reason = timezone.now(), actor, reason
    locked.save(update_fields=["lifted_at", "lifted_by", "lift_reason"])
    log_activity(actor=actor, operation="do_not_contact.lifted", instance=locked, changes={"reason_provided": True})
    return locked


def refuse_if_blocked(phone, *, field="raw_phone"):
    """For a marketing action on one number: a clear refusal when it is listed."""
    if is_blocked(phone):
        raise BusinessRuleError({field: "این شماره در فهرست «عدم تماس مجدد» است و به کمپین یا تماس بازاریابی برنمی‌گردد."})


# --- older calls -----------------------------------------------------------------


def legacy_texts(*, limit=200):
    """The words older calls carry and how many carry each, not yet matched."""
    rows = (
        Interaction.objects.filter(result="").values("outcome").annotate(total=Count("id"))
        .order_by("-total", "outcome")[:limit]
    )
    return [{"text": row["outcome"], "count": row["total"]} for row in rows]


def confident_match(text):
    """The standard outcome these words certainly mean, or `None`.

    Certain means the same words: the outcome's name or key, letters and
    spacing unified. Nothing is guessed from similar words.
    """
    def same(value):
        return " ".join(normalize_label(value).replace("‌", " ").split())

    wanted = same(text)
    for outcome in outcomes():
        if wanted in (same(outcome.label), same(outcome.key)):
            return outcome
    return None


def match_confidently():
    """Match every older call whose words certainly name an outcome."""
    matched = 0
    for row in Interaction.objects.filter(result="").values_list("outcome", flat=True).distinct():
        outcome = confident_match(row)
        if outcome is not None:
            matched += Interaction.objects.filter(result="", outcome=row).update(
                result=outcome.key, result_standard=outcome.standard_key,
            )
    return matched


def _require_mapper(actor):
    if not has_any_capability(actor, CAPABILITY) or not feature_enabled("leads"):
        raise BusinessPermissionDenied("نگاشت تماس‌های قدیمی مجاز نیست.")


@transaction.atomic
def map_legacy(*, actor, text, result):
    """Match every older call carrying exactly `text` to one outcome. Their
    words stay as they were; only the outcome is added."""
    _require_mapper(actor)
    outcome = next((item for item in outcomes(active_only=True) if item.key == str(result or "")), None)
    if outcome is None:
        raise BusinessRuleError({"result": "نتیجه را از فهرست انتخاب کنید."})
    calls = list(Interaction.objects.filter(result="", outcome=str(text)).only("pk", "normalized_phone", "notes"))
    if not calls:
        raise BusinessConflictError({"text": "تماس قدیمی نگاشت‌نشده‌ای با این متن نمانده است."})
    count = Interaction.objects.filter(pk__in=[call.pk for call in calls]).update(
        result=outcome.key, result_standard=outcome.standard_key,
    )
    if STANDARD[outcome.standard_key].stops_contact:
        # The same as recording it today: the number leaves marketing calls.
        for call in calls:
            block_number(actor=actor, phone=call.normalized_phone, interaction=call, note=call.notes[:300])
    log_activity(actor=actor, operation="call_outcome.legacy_mapped", instance=outcome, changes={"calls": count})
    return count


# --- company outcomes ------------------------------------------------------------


def can_configure(user):
    return feature_enabled(FEATURE) and has_any_capability(user, CAPABILITY)


def _require_configurer(actor):
    if not can_configure(actor):
        raise BusinessPermissionDenied("تعریف نتیجهٔ تماس مجاز نیست.")


def _clean_label(value, *, exclude=None):
    label = clean_label(value)
    if not label:
        raise BusinessRuleError({"label": "نام را بنویسید."})
    if len(label) > PIPELINE_LABEL_MAX_LENGTH:
        raise BusinessRuleError({"label": f"نام نباید بیش از {PIPELINE_LABEL_MAX_LENGTH} نویسه باشد."})
    others = CallOutcome.objects.exclude(pk=exclude).values_list("label", flat=True)
    if normalize_label(label) in {normalize_label(other) for other in others}:
        raise BusinessRuleError({"label": "این نام در فهرست هست."})
    return label


@transaction.atomic
def create_outcome(*, actor, label, standard_key):
    """A company outcome, counted in the reports as `standard_key`."""
    _require_configurer(actor)
    if standard_key not in STANDARD:
        raise BusinessRuleError({"standard_key": "نتیجهٔ استانداردی را که این نتیجه با آن شمرده شود انتخاب کنید."})
    existing = list(CallOutcome.objects.select_for_update().order_by("position", "id"))
    if sum(1 for item in existing if not item.is_system) >= MAX_COMPANY_OUTCOMES:
        raise BusinessRuleError({"label": f"حداکثر {MAX_COMPANY_OUTCOMES} نتیجهٔ اختصاصی."})
    numbers = [int(item.key[1:]) for item in existing if item.key[:1] == "c" and item.key[1:].isdigit()]
    outcome = CallOutcome.objects.create(
        key=f"c{max(numbers, default=0) + 1}", label=_clean_label(label), standard_key=standard_key,
        position=max((item.position for item in existing), default=0) + 1,
    )
    log_activity(actor=actor, operation="call_outcome.created", instance=outcome, changes={"standard": standard_key})
    return outcome


@transaction.atomic
def update_outcome(*, actor, outcome, **changes):
    """Rename any outcome; turn a company one off or on. A standard one stays on
    and keeps its meaning, and a company one keeps the standard it counts as —
    otherwise the calls already recorded with it would change meaning."""
    _require_configurer(actor)
    locked = CallOutcome.objects.select_for_update().get(pk=outcome.pk)
    unknown = set(changes) - {"label", "is_active"}
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    changed = []
    if "label" in changes:
        label = _clean_label(changes["label"], exclude=locked.pk)
        if label != locked.label:
            locked.label = label
            changed.append("label")
    if "is_active" in changes and bool(changes["is_active"]) != locked.is_active:
        if locked.is_system:
            raise BusinessRuleError({"is_active": "نتیجه‌های استاندارد همیشه روشن‌اند."})
        locked.is_active = bool(changes["is_active"])
        changed.append("is_active")
    if changed:
        locked.save(update_fields=[*changed, "updated_at"])
        log_activity(actor=actor, operation="call_outcome.updated", instance=locked, changes={"fields": sorted(changed)})
    return locked


def counts_for(interactions):
    """Calls, successful calls and qualified calls in one pass (one query)."""
    from django.db.models import Q

    row = interactions.aggregate(
        calls=Count("id"),
        successful=Count("id", filter=Q(result_standard__in=SUCCESSFUL)),
        qualified=Count("id", filter=Q(qualified=True)),
    )
    return row["calls"], row["successful"], row["qualified"]


def is_after_sales_agent(user):
    return user.role == User.Role.SALES_AGENT and user.workstream == User.Workstream.AFTER_SALES
