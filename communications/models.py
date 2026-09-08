from django.conf import settings
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


class OutboundSMS(TimeStampedModel):
    """One attempt to send an SMS this deployment originated.

    Unlike `InboundSMS`, the body is retained: this codebase wrote it, not a
    third party, so the privacy reasoning that keeps an inbound body out of the
    database does not apply — and a support agent re-reading what was actually
    sent is the whole point of keeping a log at all.

    A row is written for every attempt, successful or not — `status` records
    the outcome instead of the write failing, so a failed send is still an
    auditable fact rather than a silently swallowed exception. `send_outbound_
    sms` (communications/services.py) is the only place that creates one.
    """

    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    provider_code = models.CharField(max_length=50)
    recipient_normalized = models.CharField(max_length=20, db_index=True)
    body_text = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    status_detail = models.CharField(max_length=255, blank=True)
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="outbound_sms_messages",
    )
    lead = models.ForeignKey(
        Lead,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="outbound_sms_messages",
    )
    sent_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    sent_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    class Meta:
        ordering = ["-sent_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(provider_code__regex=r"\A[a-z0-9][a-z0-9_-]{0,49}\Z"),
                name="outbound_sms_provider_code_shape",
            ),
            models.CheckConstraint(
                condition=Q(recipient_normalized__regex=r"\A\+[1-9][0-9]{7,14}\Z"),
                name="outbound_sms_recipient_e164",
            ),
            models.CheckConstraint(
                condition=Q(body_text__regex=r"\S"),
                name="outbound_sms_body_nonblank",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["sent", "failed"]),
                name="outbound_sms_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(lead__isnull=True) | Q(customer__isnull=False),
                name="outbound_sms_lead_requires_customer",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "-sent_at"]),
            models.Index(fields=["lead", "-sent_at"]),
            models.Index(fields=["status", "-sent_at"]),
        ]


class SmsProviderSettings(TimeStampedModel):
    """One deployment's own outbound SMS gateway configuration.

    Singleton, same pattern and reasoning as `common.models.BrandSettings`:
    one deployment, one gateway. Before this model existed, the only way to
    configure `communications/sms.py`'s generic HTTP provider was
    `DOLPHIN_SMS_*` environment variables — real, but only an operator with
    host access could change them, and only by editing `.env` and restarting
    the `web` container. This row lets a Platform Admin do the same thing
    from the panel itself, for a deployment whose gateway needs a login/token
    step (`AuthMode.OAUTH2_PASSWORD`) that a static header alone cannot
    express. `communications.sms.resolve_config()` checks this row first and
    falls back to the environment variables only when this row is absent or
    disabled — see that function for the exact precedence.

    **`token_password` is stored as plain text in this table**, not
    encrypted. This is a real, acknowledged gap, not an oversight: this
    codebase has no field-level encryption-at-rest mechanism anywhere yet
    (no KMS, no `cryptography`-backed column type — see the note beside
    `DEPLOYMENT_MANIFEST_PUBLIC_KEYS` verification in `common/deployment/
    profile.py` for why `cryptography` itself is not a dependency here), and
    building one for a single field would be inventing infrastructure this
    task was not asked to build. It is no worse than the environment-variable
    alternative it replaces (`DOLPHIN_SMS_API_HEADERS` is also plaintext,
    readable to anyone with host or container access) and stays strictly
    better in one respect: it is never returned by the read API
    (`SmsProviderSettingsSerializer` exposes only `has_token_password`), never
    written to `auditlog` (`communications.sms_provider_settings.
    update_sms_provider_settings` logs field *names* changed, never values),
    and ordinary Postgres role privileges (`scripts/bootstrap-postgres.sh`)
    already restrict which database role can read this table at all.
    """

    SINGLETON = 1

    class AuthMode(models.TextChoices):
        #: A static header/query value the gateway never expires — most
        #: Iranian SMS gateways (Kavenegar, Melipayamak, Ghasedak, ...) work
        #: this way. Exactly what `communications/sms.py`'s original
        #: environment-variable-only provider already did.
        API_KEY = "api_key", "کلید ثابت (هدر/بدنه)"
        #: A username/password login call returns a short-lived bearer token
        #: (RFC 6749 "Resource Owner Password Credentials" grant), sent on
        #: every later request as `Authorization: Bearer <token>`. TIARA's own
        #: gateway (payamsms.com) is the first real example of this shape —
        #: see docs/ops/TIARA_SMS_SETUP.md.
        OAUTH2_PASSWORD = "oauth2_password", "OAuth2 (نام‌کاربری و رمز عبور)"

    class NumberStyle(models.TextChoices):
        """How the recipient number is written into the outgoing request.

        `communications.services.send_outbound_sms` always resolves a
        recipient to this codebase's own canonical E.164 form
        (`+98912xxxxxxx` — `common.phones.normalize_customer_phone`) before
        calling the provider. Not every gateway accepts that literally; this
        setting is the one, generic place that difference is absorbed, so
        `communications/sms.py` never has to guess or hardcode a vendor's
        preference.
        """

        E164 = "e164", "+۹۸۹۱۲xxxxxxx (بدون تغییر)"
        DIGITS_ONLY = "digits_only", "۹۸۹۱۲xxxxxxx (بدون +)"
        LOCAL_ZERO = "local_zero", "۰۹۱۲xxxxxxx (صفر ابتدایی)"

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON)
    #: Off by default, the same reasoning `communications.sms.provider_is_
    #: available` already documents: a control that cannot act must never be
    #: offered. A deployment that fills in every other field but leaves this
    #: unchecked is still "not configured" — an admin drafting the settings
    #: is not the same as an admin confirming them.
    is_enabled = models.BooleanField(default=False)
    #: The admin's own label for whichever gateway this is — free text,
    #: shown back to them on the settings page and in the outbound SMS log's
    #: provider column. Never used in any request; purely for a human reading
    #: this deployment's own settings to recognise what they configured.
    label = models.CharField(max_length=120, blank=True)
    auth_mode = models.CharField(max_length=20, choices=AuthMode.choices, default=AuthMode.API_KEY)
    recipient_number_style = models.CharField(
        max_length=20, choices=NumberStyle.choices, default=NumberStyle.E164
    )
    send_url = models.CharField(max_length=500, blank=True)
    #: A JSON object, parsed then substituted — identical mechanism to the
    #: legacy `DOLPHIN_SMS_API_BODY_TEMPLATE`, including its three
    #: placeholder tokens plus the new `__SMS_ID__` (see `communications/
    #: sms.py`). May be a JSON array at the root (TIARA's own `/panel/
    #: webservice/send` expects one) — substitution recurses into lists too.
    body_template = models.TextField(blank=True)
    #: A JSON object of extra static HTTP headers, merged in after
    #: `Content-Type` and (in `oauth2_password` mode) after `Authorization`,
    #: so a header named either of those here can only ever narrow what
    #: reaches the wire, never override the two this module sets itself.
    headers = models.TextField(blank=True)
    sender_id = models.CharField(max_length=32, blank=True)
    timeout_seconds = models.PositiveSmallIntegerField(default=10)

    # --- oauth2_password mode only ------------------------------------------
    token_url = models.CharField(max_length=500, blank=True)
    token_username = models.CharField(max_length=255, blank=True)
    token_password = models.CharField(max_length=255, blank=True)
    #: A JSON object of extra query parameters sent alongside `username`/
    #: `password` on the token request — e.g. TIARA's own `systemName`,
    #: `scope` and `grant_type`. Generic on purpose: RFC 6749's password
    #: grant only mandates `grant_type`/`username`/`password`/`scope`, and a
    #: real gateway is free to require more.
    token_extra_params = models.TextField(blank=True)

    #: Optional: a GET endpoint the settings page's own "تست اتصال" button
    #: calls with whatever auth this row resolves to, so an admin can see a
    #: real response (e.g. TIARA's own `/accounting/webservice/balance`)
    #: without leaving the settings page or sending a real SMS to find out
    #: whether the credentials work at all.
    test_url = models.CharField(max_length=500, blank=True)

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(auth_mode__in=["api_key", "oauth2_password"]),
                name="sms_provider_settings_auth_mode_valid",
            ),
            models.CheckConstraint(
                condition=Q(recipient_number_style__in=["e164", "digits_only", "local_zero"]),
                name="sms_provider_settings_number_style_valid",
            ),
        ]

    def __str__(self):
        return self.label or self.get_auth_mode_display()
