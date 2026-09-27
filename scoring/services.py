"""`ScoringService` — computing, storing and reading person scores (2.20.0).

A score is recomputed three ways (decision D21 / plan §6.1):

- nightly, for everyone, by `manage.py recalculate_person_scores`;
- on demand, when a profile is opened and its newest snapshot is older than
  `STALE_AFTER`;
- right after events that move it (a task done, a call — later phases call
  `refresh(...)`).

A snapshot is stored only when something changed or the last one is a day
old, so the history is one point per day at most unless the score moves.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from accounts.access import crm_identities
from accounts.models import User
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from scoring.models import PersonScore, ScoringSettings
from scoring.strategies import STRATEGIES

STALE_AFTER = timedelta(hours=24)
MAX_WEIGHT = 100

LEVELS = (
    (80, "excellent", "عالی", "success"),
    (60, "good", "خوب", "primary"),
    (40, "fair", "متوسط", "warning"),
    (0, "weak", "ضعیف", "danger"),
)
LEVEL_LABELS = {key: (label, accent) for _, key, label, accent in LEVELS}


def level_for(score):
    for floor, key, _, _ in LEVELS:
        if score >= floor:
            return key
    return "weak"


def strategy_for(person_type):
    return STRATEGIES.get(person_type)


def _settings_row():
    row, _ = ScoringSettings.objects.get_or_create(singleton=ScoringSettings.SINGLETON)
    return row


def weights_for(person_type, *, row=None):
    """`{factor: weight}` — the deployment's own weight where set, else the default."""
    strategy = strategy_for(person_type)
    row = row or _settings_row()
    stored = row.customer_weights if person_type == "customer" else row.user_weights
    return {
        factor.key: int(stored.get(factor.key, factor.default_weight))
        for factor in strategy.factors
    }


def compute_many(person_type, people, *, now=None, weights=None):
    """`{person pk: result or None}`; `None` when no factor could be measured."""
    now = now or timezone.now()
    strategy = strategy_for(person_type)
    weights = weights or weights_for(person_type)
    labels = {factor.key: factor.label for factor in strategy.factors}
    context = strategy.prepare(people, now=now)
    output = {}
    for person in people:
        factors = strategy.evaluate(person, context, now=now)
        breakdown = []
        earned = possible = 0.0
        for result in factors:
            weight = weights.get(result.key, 0)
            applicable = result.ratio is not None and weight > 0
            points = round(weight * result.ratio, 1) if applicable else 0
            if applicable:
                earned += weight * result.ratio
                possible += weight
            breakdown.append({
                "key": result.key,
                "label": labels[result.key],
                "weight": weight,
                "points": points,
                "applicable": result.ratio is not None,
                "reason": result.reason,
            })
        if not possible:
            output[person.pk] = None
            continue
        score = max(0, min(100, round(100 * earned / possible)))
        output[person.pk] = {
            "score": score,
            "level": level_for(score),
            "breakdown": breakdown,
            "strategy": strategy.key,
        }
    return output


def latest(person_type, person_id):
    return (
        PersonScore.objects.filter(person_type=person_type, person_id=person_id)
        .order_by("-computed_at", "-id")
        .first()
    )


_LOOK_IT_UP = object()


def _store(person_type, person_id, result, *, now, previous=_LOOK_IT_UP):
    """Store `result` unless it repeats the newest snapshot within a day.
    `previous` may be passed in (possibly `None`) to save the lookup."""
    if previous is _LOOK_IT_UP:
        previous = latest(person_type, person_id)
    if (
        previous is not None
        and previous.score == result["score"]
        and previous.breakdown == result["breakdown"]
        and now - previous.computed_at < STALE_AFTER
    ):
        return previous
    return PersonScore.objects.create(
        person_type=person_type,
        person_id=person_id,
        score=result["score"],
        level=result["level"],
        breakdown=result["breakdown"],
        strategy=result["strategy"],
        computed_at=now,
    )


def refresh(person_type, person, *, now=None):
    """Recompute one person now and store it if it moved; the newest snapshot."""
    if not feature_enabled("person_scoring") or strategy_for(person_type) is None:
        return None
    now = now or timezone.now()
    result = compute_many(person_type, [person], now=now)[person.pk]
    if result is None:
        return latest(person_type, person.pk)
    return _store(person_type, person.pk, result, now=now)


def current_score(person_type, person, *, now=None):
    """The newest snapshot, recomputed first if it is missing or stale."""
    if not feature_enabled("person_scoring") or strategy_for(person_type) is None:
        return None
    now = now or timezone.now()
    snapshot = latest(person_type, person.pk)
    if snapshot is None or now - snapshot.computed_at >= STALE_AFTER:
        return refresh(person_type, person, now=now)
    return snapshot


def history(person_type, person_id, *, limit=30):
    return list(
        PersonScore.objects.filter(person_type=person_type, person_id=person_id)
        .order_by("-computed_at", "-id")[:limit]
    )


def scorable_people(person_type):
    if person_type == "customer":
        from sales.models import Customer

        return Customer.objects.filter(is_active=True).order_by("pk")
    return crm_identities(User.objects.filter(is_active=True)).order_by("pk")


def recalculate_all(person_types=("customer", "user"), *, now=None, batch_size=200):
    """Score everyone; `{person_type: (computed, stored)}`. Idempotent: a run
    that changes nothing stores nothing (within a day)."""
    if not feature_enabled("person_scoring"):
        return {}
    now = now or timezone.now()
    summary = {}
    for person_type in person_types:
        weights = weights_for(person_type)
        computed = stored = 0
        queryset = scorable_people(person_type)
        start = 0
        while True:
            batch = list(queryset[start:start + batch_size])
            if not batch:
                break
            start += batch_size
            results = compute_many(person_type, batch, now=now, weights=weights)
            previous = {}
            for row in PersonScore.objects.filter(
                person_type=person_type, person_id__in=[person.pk for person in batch]
            ).order_by("person_id", "-computed_at", "-id"):
                previous.setdefault(row.person_id, row)
            for person in batch:
                result = results[person.pk]
                if result is None:
                    continue
                computed += 1
                before = previous.get(person.pk)
                after = _store(person_type, person.pk, result, now=now, previous=before)
                if after is not before:
                    stored += 1
        summary[person_type] = (computed, stored)
    return summary


@transaction.atomic
def update_weights(*, actor, person_type, weights):
    """Platform Admin sets how much each factor counts (0–100 each)."""
    if actor.role != User.Role.PLATFORM_ADMIN:
        raise BusinessPermissionDenied("تنظیم وزن‌های امتیازدهی فقط برای مدیر پلتفرم مجاز است.")
    if not feature_enabled("person_scoring"):
        raise BusinessPermissionDenied("امتیازدهی در این استقرار فعال نیست.")
    strategy = strategy_for(person_type)
    if strategy is None:
        raise BusinessRuleError({"person_type": "نوع شخص نامعتبر است."})
    known = {factor.key for factor in strategy.factors}
    if not isinstance(weights, dict) or set(weights) - known:
        raise BusinessRuleError({"weights": "عامل ناشناخته‌ای فرستاده شده است."})
    cleaned = {}
    for key, value in weights.items():
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_WEIGHT:
            raise BusinessRuleError({key: f"وزن باید عددی صحیح بین ۰ و {MAX_WEIGHT} باشد."})
        cleaned[key] = value
    if not any(cleaned.get(factor.key, factor.default_weight) for factor in strategy.factors):
        raise BusinessRuleError({"weights": "دست‌کم یک عامل باید وزن داشته باشد."})
    row = ScoringSettings.objects.select_for_update().get_or_create(singleton=ScoringSettings.SINGLETON)[0]
    if person_type == "customer":
        row.customer_weights = cleaned
    else:
        row.user_weights = cleaned
    row.updated_by = actor
    row.save()
    log_activity(actor=actor, operation="scoring.weights_updated", instance=row, changes={"fields": sorted(cleaned)})
    return weights_for(person_type, row=row)
