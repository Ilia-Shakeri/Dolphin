"""Which campaign a valid invoice counts for (2.36.0).

A *valid* invoice is an issued one that is not cancelled. A person converts in a
campaign only when such an invoice is issued to their customer record after they
entered the campaign; being a customer already is a flag
(`was_customer_on_entry`), never a conversion.

Automatic attribution is **last touch**: of the campaigns this customer's phone
numbers sit in, the one whose person was most recently contacted (or entered)
inside the window wins. A manager may correct the link by hand with a reason.
Only the link is ever changed — never the invoice — and every change is logged.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.access import has_any_capability
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from sales.models import Campaign, CampaignAttribution, CampaignAttributionLog, Interaction, TargetAudienceMember

logger = logging.getLogger("dolphin.campaigns")


def window_days():
    return int(getattr(settings, "CAMPAIGN_ATTRIBUTION_WINDOW_DAYS", 30))


def _last_touch(member):
    last = member.interactions.order_by("-occurred_at").values_list("occurred_at", flat=True).first()
    return last or member.created_at


def _candidates(invoice, at):
    from sales.models import CustomerPhone

    phones = list(
        CustomerPhone.objects.filter(customer_id=invoice.customer_id, is_active=True)
        .exclude(normalized_phone="").values_list("normalized_phone", flat=True)
    )
    if not phones:
        return []
    cutoff = at - timedelta(days=window_days())
    members = (
        TargetAudienceMember.objects.select_related("campaign")
        .filter(normalized_phone__in=phones, campaign__isnull=False, created_at__lte=at)
        .exclude(campaign__status=Campaign.Status.ARCHIVED)
        .exclude(campaign__system_key__in=["direct", "referral", "legacy"])
        .exclude(stage=TargetAudienceMember.Stage.LOST)
    )
    scored = [(member, _last_touch(member)) for member in members]
    return sorted((pair for pair in scored if cutoff <= pair[1] <= at), key=lambda pair: pair[1], reverse=True)


def _mark_converted(member, at):
    if member.stage != TargetAudienceMember.Stage.CONVERTED:
        member.stage = TargetAudienceMember.Stage.CONVERTED
        member.converted_at = at
        member.save(update_fields=["stage", "converted_at", "updated_at"])


def _release_member(member):
    """Take a person back out of «تبدیل‌شده» when no valid invoice backs it."""
    from billing.models import Invoice

    still_backed = CampaignAttribution.objects.filter(
        member=member, invoice__status=Invoice.Status.ISSUED
    ).exists()
    if still_backed or member.stage != TargetAudienceMember.Stage.CONVERTED:
        return
    if Interaction.objects.filter(target_member=member).exists():
        stage = TargetAudienceMember.Stage.ENGAGED
    else:
        stage = TargetAudienceMember.Stage.NEW
    member.stage, member.converted_at = stage, None
    member.save(update_fields=["stage", "converted_at", "updated_at"])


def attribute_issued_invoice(*, invoice, issued_at):
    """Called by billing right after an invoice is issued.

    Runs in a savepoint: a campaign-side failure must never block issuing an
    invoice, but it is logged with its traceback, never swallowed silently.
    A deployment without the `campaigns` feature is untouched.
    """
    if not feature_enabled("campaigns"):
        return None
    try:
        with transaction.atomic():
            if CampaignAttribution.objects.filter(invoice=invoice).exists():
                return None
            ranked = _candidates(invoice, issued_at)
            if not ranked:
                return None
            member, _touched = ranked[0]
            attribution = CampaignAttribution.objects.create(
                invoice=invoice, campaign=member.campaign, member=member, source=CampaignAttribution.Source.AUTO
            )
            CampaignAttributionLog.objects.create(
                invoice=invoice, to_campaign=member.campaign, source="auto"
            )
            _mark_converted(member, issued_at)
            return attribution
    except Exception:  # noqa: BLE001 - see docstring: logged, never blocks issuing
        logger.exception("campaign attribution failed for invoice %s", invoice.pk)
        return None


def release_cancelled_invoice(*, invoice):
    """Called by billing after a cancellation: the invoice no longer counts."""
    if not feature_enabled("campaigns"):
        return
    try:
        with transaction.atomic():
            attribution = CampaignAttribution.objects.select_related("member").filter(invoice=invoice).first()
            if attribution is not None and attribution.member is not None:
                _release_member(attribution.member)
    except Exception:  # noqa: BLE001 - same contract as attribute_issued_invoice
        logger.exception("campaign release failed for invoice %s", invoice.pk)


@transaction.atomic
def attribute_manually(*, actor, invoice, campaign, reason):
    """Point a valid invoice at a different campaign. Reason is required.

    Only an issued invoice can be attributed; a draft has no revenue yet and a
    cancelled one never counts.
    """
    from billing.models import Invoice

    if not has_any_capability(actor, "campaigns.attribute"):
        raise BusinessPermissionDenied("تغییر کمپین فاکتور مجاز نیست.")
    reason = str(reason or "").strip()
    if not reason:
        raise BusinessRuleError({"reason": "دلیل تغییر را بنویسید."})
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status != Invoice.Status.ISSUED:
        raise BusinessConflictError({"invoice": "فقط فاکتور صادرشده را می‌توان به کمپین نسبت داد."})
    campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    existing = CampaignAttribution.objects.select_for_update().filter(invoice=locked).first()
    if existing is not None and existing.campaign_id == campaign.pk:
        raise BusinessConflictError({"campaign": "فاکتور هم‌اکنون به همین کمپین نسبت داده شده است."})
    previous_member = existing.member if existing else None
    previous_campaign = existing.campaign if existing else None
    # The person who stood behind this invoice in the *new* campaign, if any.
    from sales.models import CustomerPhone

    phones = CustomerPhone.objects.filter(customer_id=locked.customer_id, is_active=True).values_list("normalized_phone", flat=True)
    member = TargetAudienceMember.objects.filter(campaign=campaign, normalized_phone__in=list(phones)).first()
    if existing is None:
        CampaignAttribution.objects.create(
            invoice=locked, campaign=campaign, member=member,
            source=CampaignAttribution.Source.MANUAL, attributed_by=actor, reason=reason[:500],
        )
    else:
        existing.campaign, existing.member = campaign, member
        existing.source, existing.attributed_by, existing.reason = CampaignAttribution.Source.MANUAL, actor, reason[:500]
        existing.save(update_fields=["campaign", "member", "source", "attributed_by", "reason", "updated_at"])
    CampaignAttributionLog.objects.create(
        invoice=locked, from_campaign=previous_campaign, to_campaign=campaign,
        source="manual", actor=actor, reason=reason[:500],
    )
    if previous_member is not None:
        _release_member(previous_member)
    if member is not None:
        _mark_converted(member, locked.issued_at or timezone.now())
    log_activity(
        actor=actor, operation="invoice.campaign_attributed", instance=locked,
        changes={"from": previous_campaign.pk if previous_campaign else None, "to": campaign.pk},
    )
    return CampaignAttribution.objects.get(invoice=locked)
