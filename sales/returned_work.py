"""Work that comes back to the managers when its owner is deactivated (2.40.48).

Owner decision 2026-10-14 (BIZ-013): «به مدیر برگردد و به مدیر اخطار بدهد و بگوید
که تصمیم بگیرد، و مدیر باید گزینهٔ تقسیم میان بقیهٔ مسئولان را داشته باشد».

* **Return.** When an account is deactivated (`accounts.signals.user_deactivated`,
  in the same transaction), its open leads and its open campaign people lose
  their assignee and are marked `returned_from` that person. Finished work —
  a completed or cancelled lead, a converted or lost person — stays theirs;
  it is history, not work.
* **Alert.** Dolphin has no "this marketer's manager" relation, so every store
  manager (and anyone else who manages company leads) sees it: the reminder
  bell lists one entry per returned person until the work has a new owner
  (`common.reminders`), and the leads page offers the decision.
* **Decide.** Split it evenly among the other responsibles of each item's own
  campaign (the same balancing as new leads, `pick_balanced_assignee`), with
  people the manager picks for anything that has no campaign or no other
  active responsible; or hand it all to one person; or assign items one by one
  from their own pages. Any assignment clears the mark.

Nothing is deleted and nothing is reassigned without a manager's decision.
"""

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from accounts.access import capabilities_for, is_crm_identity
from accounts.models import User
from auditlog.services import log_activity
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from sales.models import Lead, LeadAssignmentHistory, TargetAudienceMember
from sales.selectors import leads_for, target_audience_for
from sales.services import (
    ELEVATED_OPERATORS,
    _can_work_leads,
    _lock_active_actor,
    campaign_lead_assignees,
    pick_balanced_assignee,
)

OPEN_LEAD_STATUSES = (Lead.Status.PENDING, "")
CLOSED_MEMBER_STAGES = (TargetAudienceMember.Stage.CONVERTED, TargetAudienceMember.Stage.LOST)
RESOLVE_ACTIONS = ("split", "assign")


def return_work_of(*, actor, user):
    """Take `user`'s open work back to the managers. Called inside the
    transaction that deactivates them; returns `(lead_count, member_count)`."""
    now = timezone.now()
    leads = (
        Lead.objects.select_for_update()
        .filter(assigned_to=user, status__in=OPEN_LEAD_STATUSES)
        .exclude(source="campaign")
    )
    # The assignee, who assigned it and when go together (a database check).
    lead_count = leads.update(
        assigned_to=None, assigned_by=None, assigned_at=None, returned_from=user, returned_at=now, updated_at=now
    )
    members = (
        TargetAudienceMember.objects.select_for_update()
        .filter(assigned_to=user)
        .exclude(stage__in=CLOSED_MEMBER_STAGES)
    )
    member_count = members.update(
        assigned_to=None, assigned_by=None, assigned_at=None, returned_from=user, returned_at=now, updated_at=now
    )
    if lead_count or member_count:
        log_activity(
            actor=actor,
            operation="user.work_returned",
            instance=user,
            changes={"lead_count": lead_count, "member_count": member_count},
        )
    return lead_count, member_count


def can_decide_returned_work(user):
    capabilities = capabilities_for(user)
    return (
        is_crm_identity(user)
        and user.role in ELEVATED_OPERATORS
        and "leads.company" in capabilities
        and "leads.manage" in capabilities
    )


def returned_leads_for(user):
    if not can_decide_returned_work(user):
        return Lead.objects.none()
    return leads_for(user).filter(returned_from__isnull=False, assigned_to__isnull=True)


def returned_members_for(user):
    if not can_decide_returned_work(user):
        return TargetAudienceMember.objects.none()
    return target_audience_for(user).filter(returned_from__isnull=False, assigned_to__isnull=True)


def returned_work_summary(user):
    """One row per person whose work is waiting for a decision, newest first."""
    rows = {}
    for queryset, kind in ((returned_leads_for(user), "lead_count"), (returned_members_for(user), "member_count")):
        for row in queryset.values("returned_from").annotate(total=Count("id"), last=Max("returned_at")):
            entry = rows.setdefault(row["returned_from"], {"lead_count": 0, "member_count": 0, "returned_at": row["last"]})
            entry[kind] = row["total"]
            entry["returned_at"] = max(entry["returned_at"], row["last"])
    people = {person.pk: person for person in User.objects.filter(pk__in=rows)}
    summary = []
    for user_id, entry in rows.items():
        person = people[user_id]
        summary.append({
            "from_user": user_id,
            "from_user_display": person.get_full_name() or person.username,
            **entry,
        })
    return sorted(summary, key=lambda item: item["returned_at"], reverse=True)


def _validated_people(ids, *, field):
    people = []
    for person in User.objects.filter(pk__in=ids or []):
        if not _can_work_leads(person):
            raise BusinessRuleError({field: "هر کدام باید کاربر فعالِ بخش فروش یا مدیریت باشد."})
        people.append(person)
    if len(people) != len(set(ids or [])):
        raise BusinessRuleError({field: "کاربری پیدا نشد."})
    return sorted(people, key=lambda person: person.pk)


def _agents_only(people):
    return [person for person in people if person.role == User.Role.SALES_AGENT]


def _least_loaded(people, load):
    fewest = min(load[person.pk] for person in people)
    return next(person for person in people if load[person.pk] == fewest)


@transaction.atomic
def resolve_returned_work(*, actor, from_user, action, to_user=None, fallback_users=None):
    """The manager's decision for everything that came back from `from_user`.

    `split`: each lead to the other responsibles of its campaign, evenly;
    anything with no campaign, or none of whose responsibles is still active,
    goes evenly to `fallback_users`, which are required only when such items
    exist. A campaign person goes to a marketer, as `assign_campaign_member`
    requires. `assign`: everything to `to_user`.
    """
    actor = _lock_active_actor(actor)
    if not can_decide_returned_work(actor):
        raise BusinessPermissionDenied("تصمیم دربارهٔ کارهای برگشتی با مدیر است.")
    if action not in RESOLVE_ACTIONS:
        raise BusinessRuleError({"action": "تصمیم نامعتبر است."})
    source = getattr(from_user, "pk", from_user)
    leads = list(
        returned_leads_for(actor).filter(returned_from_id=source).select_for_update(of=("self",)).select_related("campaign")
    )
    members = list(
        returned_members_for(actor).filter(returned_from_id=source).select_for_update(of=("self",)).select_related("campaign")
    )
    if not leads and not members:
        raise BusinessRuleError({"from_user": "کار برگشتی‌ای از این کاربر نمانده است."})

    now = timezone.now()
    plan = []  # (item, person)
    history = []

    def give(item, person):
        item.assigned_to = person
        item.assigned_by = actor
        item.assigned_at = now
        item.returned_from = None
        item.returned_at = None
        if isinstance(item, Lead):
            item.save(update_fields=["assigned_to", "assigned_by", "assigned_at", "returned_from", "returned_at", "updated_at"])
            history.append(LeadAssignmentHistory(
                lead=item, from_user_id=source, to_user=person, changed_by=actor, reason="بازگشت از کاربر غیرفعال",
            ))
        else:
            item.updated_by = actor
            item.save(update_fields=["assigned_to", "assigned_by", "assigned_at", "returned_from", "returned_at", "updated_by", "updated_at"])
        plan.append((item, person))

    if action == "assign":
        target = _validated_people([getattr(to_user, "pk", to_user)], field="to_user")[0] if to_user else None
        if target is None:
            raise BusinessRuleError({"to_user": "یک نفر را انتخاب کنید."})
        if members and target.role != User.Role.SALES_AGENT:
            raise BusinessRuleError({"to_user": "مخاطبان کمپین فقط به بازاریاب داده می‌شوند."})
        for item in [*leads, *members]:
            give(item, target)
    else:
        fallback = _validated_people(fallback_users, field="fallback_users")
        load = {person.pk: 0 for person in fallback}
        needs_fallback = 0
        for lead in leads:
            candidates = [person for person in campaign_lead_assignees(lead.campaign) if person.pk != source]
            if candidates:
                person = pick_balanced_assignee(lead.campaign, candidates)
            elif fallback:
                person = _least_loaded(fallback, load)
                load[person.pk] += 1
            else:
                needs_fallback += 1
                continue
            # Saved before the next pick, so a campaign's split stays even
            # within this one decision.
            give(lead, person)
        agent_fallback = _agents_only(fallback)
        agent_load = {person.pk: 0 for person in agent_fallback}
        for member in members:
            candidates = [
                person for person in _agents_only(campaign_lead_assignees(member.campaign)) if person.pk != source
            ]
            if candidates:
                counts = dict(
                    TargetAudienceMember.objects.filter(campaign=member.campaign, assigned_to__in=candidates)
                    .values_list("assigned_to").annotate(total=Count("id"))
                )
                fewest = min(counts.get(person.pk, 0) for person in candidates)
                person = next(person for person in candidates if counts.get(person.pk, 0) == fewest)
            elif agent_fallback:
                person = _least_loaded(agent_fallback, agent_load)
                agent_load[person.pk] += 1
            else:
                needs_fallback += 1
                continue
            give(member, person)
        if needs_fallback:
            raise BusinessRuleError({
                "fallback_users": f"{needs_fallback} مورد کمپین یا مسئول فعال دیگری ندارد؛ برای آن‌ها چند نفر را انتخاب کنید.",
            })

    LeadAssignmentHistory.objects.bulk_create(history)
    by_user = {}
    for _, person in plan:
        entry = by_user.setdefault(person.pk, {"user": person.pk, "display": person.get_full_name() or person.username, "count": 0})
        entry["count"] += 1
    log_activity(
        actor=actor,
        operation="user.returned_work_resolved",
        instance=User.objects.get(pk=source),
        changes={"lead_count": len(leads), "member_count": len(members), "action": action},
    )
    return {"assigned_count": len(plan), "by_user": sorted(by_user.values(), key=lambda entry: -entry["count"])}
