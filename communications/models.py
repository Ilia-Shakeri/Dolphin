from django.db import models
from django.db.models import Q
from django.utils import timezone

from common.models import TimeStampedModel
from sales.models import Customer, Lead


class InboundSMS(TimeStampedModel):
    class Direction(models.TextChoices):
        INBOUND = "inbound", "Inbound"

    class ProcessingState(models.TextChoices):
        UNMATCHED = "unmatched", "Unmatched"
        LINKED = "linked", "Linked"

    class BodyRetentionPolicy(models.TextChoices):
        NOT_RETAINED = "not_retained", "Not retained"

    provider_code = models.CharField(max_length=50)
    external_message_id = models.CharField(max_length=160)
    sender_normalized = models.CharField(max_length=20, db_index=True)
    recipient_normalized = models.CharField(max_length=20, db_index=True)
    provider_received_at = models.DateTimeField(db_index=True)
    system_received_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    direction = models.CharField(
        max_length=20,
        choices=Direction.choices,
        default=Direction.INBOUND,
        editable=False,
    )
    metadata = models.JSONField(default=dict, blank=True)
    body_retention_policy = models.CharField(
        max_length=24,
        choices=BodyRetentionPolicy.choices,
        default=BodyRetentionPolicy.NOT_RETAINED,
        editable=False,
    )
    processing_state = models.CharField(
        max_length=20,
        choices=ProcessingState.choices,
        default=ProcessingState.UNMATCHED,
        db_index=True,
    )
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inbound_sms_messages",
    )
    lead = models.ForeignKey(
        Lead,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inbound_sms_messages",
    )

    class Meta:
        ordering = ["-provider_received_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider_code", "external_message_id"],
                name="uniq_inbound_sms_provider_message",
            ),
            models.CheckConstraint(
                condition=Q(provider_code__regex=r"\A[a-z0-9][a-z0-9_-]{0,49}\Z"),
                name="inbound_sms_provider_code_shape",
            ),
            models.CheckConstraint(
                condition=Q(external_message_id__regex=r"\S"),
                name="inbound_sms_external_id_nonblank",
            ),
            models.CheckConstraint(
                condition=Q(sender_normalized__regex=r"\A\+[1-9][0-9]{7,14}\Z"),
                name="inbound_sms_sender_e164",
            ),
            models.CheckConstraint(
                condition=Q(recipient_normalized__regex=r"\A\+[1-9][0-9]{7,14}\Z"),
                name="inbound_sms_recipient_e164",
            ),
            models.CheckConstraint(
                condition=Q(direction="inbound"),
                name="inbound_sms_direction_only",
            ),
            models.CheckConstraint(
                condition=Q(body_retention_policy="not_retained"),
                name="inbound_sms_body_not_retained",
            ),
            models.CheckConstraint(
                condition=Q(processing_state__in=["unmatched", "linked"]),
                name="inbound_sms_processing_state_valid",
            ),
            models.CheckConstraint(
                condition=Q(lead__isnull=True) | Q(customer__isnull=False),
                name="inbound_sms_lead_requires_customer",
            ),
        ]
        indexes = [
            models.Index(fields=["provider_code", "-provider_received_at"]),
            models.Index(fields=["recipient_normalized", "-provider_received_at"]),
            models.Index(fields=["customer", "-provider_received_at"]),
            models.Index(fields=["lead", "-provider_received_at"]),
        ]
