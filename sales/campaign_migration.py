"""Move existing campaign data onto the Campaign entity (2.36.0).

`manage.py migrate_campaigns [--dry-run]` — expand-only and idempotent.

* Leads are grouped by the *normalised* `campaign_or_batch` text (letters,
  digits, spacing); each group becomes one `Campaign`, a blank label becomes
  «بدون کمپین (قدیمی)». Spellings that differ only by spacing or a half-space
  are **not** merged — they become separate campaigns and are listed under
  "needs review" so a person decides.
* Every `TargetAudienceMember` gets the campaign of its lead, and inherits that
  lead's assignee and follow-up. Nothing is rewritten: the old text label, the
  lead rows, interactions, sales and the derived `status` stay as they were, so
  the previous release keeps working on the same database.
* `was_customer_on_entry` is left unknown (`None`) for migrated people
  (2.39.24): their status today does not say whether they were a customer when
  they entered. Nobody is counted as converted by the migration — only a valid
  attributed invoice does that.
* A campaign created from a group whose leads were all «تکمیل» starts as
  «تمام‌شده», all «کنسل شده» as «بایگانی»; anything else as «فعال».
* `--report FILE.csv` writes one row per migrated person (and per review group).
"""

import csv

from dataclasses import dataclass, field

from django.db import transaction

from accounts.models import User
from sales.campaigns import ensure_system_campaigns
from sales.customer_backfill import clean_label, loose_key, normalize_label
from sales.models import Campaign, Lead, TargetAudienceMember


@dataclass
class MigrationReport:
    campaigns_to_create: int = 0
    leads_to_link: int = 0
    members_to_migrate: int = 0
    already_customers: int = 0
    lost_from_failed: int = 0
    needs_review: list = field(default_factory=list)
    rows: list = field(default_factory=list)

    def write_csv(self, path):
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["member_id", "campaign", "stage", "old_status", "note"])
            writer.writerows(self.rows)
            for group in self.needs_review:
                writer.writerow(["", " | ".join(group), "", "", "needs review: spellings differ only by spacing"])

    def lines(self):
        out = [
            f"campaigns to create: {self.campaigns_to_create}",
            f"leads to link to a campaign: {self.leads_to_link}",
            f"audience members to migrate: {self.members_to_migrate}",
            f"  flagged as already customers (not conversions): {self.already_customers}",
            f"  carried over as lost (old status 'failed'): {self.lost_from_failed}",
            f"needs review (spellings that differ only by spacing): {len(self.needs_review)}",
        ]
        out += [f"  - {' | '.join(group)}" for group in self.needs_review]
        return out


def _actor():
    actor = User.objects.filter(role=User.Role.PLATFORM_ADMIN, is_active=True).order_by("id").first()
    return actor or User.objects.filter(is_active=True).order_by("id").first()


@transaction.atomic
def run_migration(*, apply):
    report = MigrationReport()
    actor = _actor()
    if actor is None:
        return report
    legacy_name = clean_label("بدون کمپین (قدیمی)")
    labels = {}
    for lead in Lead.objects.filter(campaign__isnull=True).order_by("id"):
        key = normalize_label(lead.campaign_or_batch) or normalize_label(legacy_name)
        labels.setdefault(key, clean_label(lead.campaign_or_batch) or legacy_name)
    groups = {}
    for key, label in labels.items():
        groups.setdefault(loose_key(label), []).append(label)
    report.needs_review = [sorted(group) for group in groups.values() if len(group) > 1]

    system = ensure_system_campaigns(actor) if apply else {}
    by_key = {c.normalized_name: c for c in Campaign.objects.all()}
    statuses = {}
    for lead in Lead.objects.filter(campaign__isnull=True).only("campaign_or_batch", "status"):
        key = normalize_label(lead.campaign_or_batch) or normalize_label(legacy_name)
        statuses.setdefault(key, set()).add(lead.status)
    for key, label in labels.items():
        if key in by_key:
            continue
        report.campaigns_to_create += 1
        seen = statuses.get(key, set())
        if seen == {Lead.Status.COMPLETED}:
            status = Campaign.Status.FINISHED
        elif seen == {Lead.Status.CANCELLED}:
            status = Campaign.Status.ARCHIVED
        else:
            status = Campaign.Status.ACTIVE
        if apply:
            by_key[key] = Campaign.objects.create(
                name=label[:120], normalized_name=key[:120], status=status,
                channels=[Campaign.Channel.PHONE], created_by=actor, updated_by=actor,
            )
    if system:
        by_key.update({c.normalized_name: c for c in system.values()})

    for lead in Lead.objects.filter(campaign__isnull=True).order_by("id"):
        report.leads_to_link += 1
        if apply:
            key = normalize_label(lead.campaign_or_batch) or normalize_label(legacy_name)
            Lead.objects.filter(pk=lead.pk, campaign__isnull=True).update(campaign_id=by_key[key].pk)

    pending = TargetAudienceMember.objects.filter(campaign__isnull=True).select_related("lead")
    for member in pending.order_by("id"):
        report.members_to_migrate += 1
        customer = member.status == TargetAudienceMember.Status.CUSTOMER
        failed = member.status == TargetAudienceMember.Status.FAILED
        report.already_customers += int(customer)
        report.lost_from_failed += int(failed)
        report.rows.append([
            member.pk, member.lead.campaign_or_batch or legacy_name,
            "lost" if failed else ("contacted" if member.interactions.exists() else "new"),
            member.status, "was customer at migration (entry unknown)" if customer else "",
        ])
        if not apply:
            continue
        lead = member.lead
        campaign_id = lead.campaign_id or by_key[
            normalize_label(lead.campaign_or_batch) or normalize_label(legacy_name)
        ].pk
        if failed:
            stage = TargetAudienceMember.Stage.LOST
        elif member.interactions.exists():
            stage = TargetAudienceMember.Stage.CONTACTED
        else:
            stage = TargetAudienceMember.Stage.NEW
        TargetAudienceMember.objects.filter(pk=member.pk, campaign__isnull=True).update(
            campaign_id=campaign_id,
            assigned_to_id=lead.assigned_to_id, assigned_by_id=lead.assigned_by_id, assigned_at=lead.assigned_at,
            next_follow_up_at=lead.next_follow_up_at, stage=stage,
            lost_reason="از وضعیت قدیمی «ناموفق»" if failed else "",
            was_customer_on_entry=None,
        )
    return report
