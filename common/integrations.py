"""Every outside service this deployment can be connected to, in one table.

Product-owner request 2026-09-20: a proper page for connecting services —
the list, each one's connection status, its key or token stored securely and
shown masked, a way to test the connection, an on/off switch, and the last
error — «ساختار طوری باشد که اضافه‌کردن سرویس جدید ساده باشد».

The last clause is the design. An integration is a row here: a key, what to
call it, who may configure it, where its own settings page is, and a
callable that reports its state. Everything the page draws comes from
that row, so adding a service is one entry plus its own status function —
no template change, no new view, no second list to keep in step.

**Four rows today, and the last two are honest about being empty.** SMS is a
real, configurable, testable gateway. Post is the carrier seam from
`sales.postal` — manual in this build, with the interface a provider will be
implemented against. VoIP/telephony (product-owner request 2026-09-21,
alongside the same request that asked for every SMS/post "model" to be
connectable — see `docs/ops/PROVIDER_CONNECTION_GUIDE.md`) has no code
anywhere in this repository yet — no model, no settings page, no scope
decision — so it is a named placeholder rather than a generic one, the same
"honest about being empty" shape as the row after it. `coming_soon` stays
the generic catch-all for whatever is not even named yet (a payment gateway,
the tax-authority system). Neither offers a switch that does nothing, which
is worse than an empty space (CLAUDE.md §27).

**Nothing here is a permission.** `gate` is a callable that answers the
same question that integration's own settings page and API already answer
for themselves — a role test for SMS, a capability for post — and naming it
here only lets the list leave out a row the reader could not open anyway.
Hiding a row is not what makes it safe; the page behind it is.

**No secret is ever read out of here.** A status reports whether a
credential is set and a masked hint of it, never the value — the same rule
`communications.serializers` already applies to `token_password`.
"""

from dataclasses import dataclass
from typing import Callable


def mask_secret(value, *, keep=4):
    """A credential as a hint rather than a value.

    Shows the last few characters of anything long enough for that to be
    meaningless on its own, and nothing at all otherwise — a four-character
    secret shown "masked" as its last four characters is not masked.
    """
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= keep * 2:
        return "•" * len(text)
    return "•" * (len(text) - keep) + text[-keep:]


@dataclass(frozen=True)
class IntegrationStatus:
    """What one integration can say about itself right now.

    `state` is one of `connected`, `configured`, `disabled`, `unconfigured`
    or `unavailable`, and the distinction between the first four is the
    whole point of the page:

    * `connected`    — configured, switched on, and the last attempt worked;
    * `configured`   — set up and on, but nothing has been sent through it
                       yet, so nobody can claim it works;
    * `disabled`     — set up and deliberately switched off;
    * `unconfigured` — nothing has been entered;
    * `unavailable`  — this build cannot offer it at all («به‌زودی»).
    """

    state: str
    summary: str
    #: A masked credential hint, or "" when there is nothing to hint at.
    secret_hint: str = ""
    #: The last thing that went wrong, verbatim from the provider where the
    #: provider said it. Empty when nothing has.
    last_error: str = ""
    #: When that error happened, as an aware datetime, or `None`.
    last_error_at: object = None


#: The five states, and what each is called and coloured in the panel. Kept
#: beside the states rather than in the template for the same reason the
#: postal icons sit beside the postal states: one table, one place to change.
STATE_LABELS = {
    "connected": ("متصل", "success"),
    "configured": ("پیکربندی‌شده", "primary"),
    "disabled": ("غیرفعال", "warning"),
    "unconfigured": ("پیکربندی نشده", "secondary"),
    "unavailable": ("به‌زودی", "secondary"),
}


@dataclass(frozen=True)
class Integration:
    key: str
    label: str
    description: str
    icon: str
    icon_paths: int
    #: `(user) -> bool`, mirroring the gate that integration's own page
    #: enforces. `None` for a placeholder nobody configures.
    gate: Callable = None
    #: The deployment feature it belongs to, so a module this customer does
    #: not license leaves no row behind.
    feature: str = None
    #: Its own settings page, or `None` for one with nothing to open.
    settings_url_name: str = None
    #: `POST` here to test the connection, or `None` where no test exists.
    #: A test that cannot really be run is not offered.
    test_url: str = None
    #: `(user) -> IntegrationStatus`.
    status: Callable = None
    #: Extra facts worth showing under the row, `[(label, value)]`.
    details: Callable = None


def _platform_admin_role():
    from accounts.models import User

    return User.Role.PLATFORM_ADMIN


def _has(user, capability):
    from common.permissions import has_any_capability

    return has_any_capability(user, capability)


# --- the status functions ----------------------------------------------------


def _sms_status(_user):
    from communications import sms
    from communications.models import OutboundSMS, SmsProviderSettings

    row = SmsProviderSettings.objects.filter(
        singleton=SmsProviderSettings.SINGLETON
    ).first()
    config = sms.resolve_config()

    # The last failure, whatever configured it. `status_detail` is what the
    # provider itself said, which is the only useful thing to show an
    # operator who is looking at this page because something is wrong.
    failure = (
        OutboundSMS.objects.filter(status=OutboundSMS.Status.FAILED)
        .order_by("-created_at")
        .values("status_detail", "created_at")
        .first()
    )
    last_error = (failure or {}).get("status_detail") or ""
    last_error_at = (failure or {}).get("created_at")

    if config is None:
        return IntegrationStatus(
            state="disabled" if row is not None and not row.is_enabled else "unconfigured",
            summary=(
                "تنظیمات ذخیره شده ولی خاموش است."
                if row is not None and not row.is_enabled
                else "هنوز هیچ درگاهی پیکربندی نشده است."
            ),
            last_error=last_error,
            last_error_at=last_error_at,
        )

    # Something has gone through: the one honest basis for "connected".
    delivered = OutboundSMS.objects.filter(status=OutboundSMS.Status.SENT).exists()
    return IntegrationStatus(
        state="connected" if delivered else "configured",
        summary=(
            f"درگاه «{row.label}» فعال است."
            if row is not None and row.label
            else "درگاه از متغیرهای محیطی خوانده می‌شود."
        ),
        secret_hint=mask_secret(getattr(row, "token_password", "") if row else ""),
        last_error=last_error,
        last_error_at=last_error_at,
    )


def _sms_details(_user):
    from communications.models import SmsProviderSettings

    row = SmsProviderSettings.objects.filter(
        singleton=SmsProviderSettings.SINGLETON
    ).first()
    if row is None:
        return [("منبع تنظیمات", "متغیرهای محیطی")]
    return [
        ("منبع تنظیمات", "پنل"),
        ("شیوهٔ احراز", row.get_auth_mode_display()),
        ("نشانی ارسال", row.send_url or "—"),
        ("شناسهٔ فرستنده", row.sender_id or "—"),
    ]


def _post_status(_user):
    from sales.postal import carrier_for
    from sales.postal_provider import get_post_provider_settings

    carrier = carrier_for(None)
    row = get_post_provider_settings()
    manual_summary = (
        "وضعیت مرسوله‌ها دستی ثبت می‌شود. رابط اتصال به سرویس پست آماده "
        "است و با افزوده‌شدن یک ارائه‌دهنده، همین چهار حالت را پر می‌کند."
    )
    if carrier.supports_tracking:
        return IntegrationStatus(state="configured", summary=carrier.label)
    if row.is_enabled and row.base_url:
        return IntegrationStatus(
            state="configured",
            summary=f"اتصال «{row.label}» ذخیره شده و فعال است — {manual_summary}",
            secret_hint=mask_secret(row.api_key),
        )
    if row.base_url or row.api_key:
        return IntegrationStatus(
            state="disabled",
            summary=f"تنظیمات ذخیره شده ولی خاموش است. {manual_summary}",
            secret_hint=mask_secret(row.api_key),
        )
    return IntegrationStatus(state="unconfigured", summary=manual_summary)


def _post_details(_user):
    from sales.postal import POSTAL_STATES, carrier_for
    from sales.postal_provider import get_post_provider_settings

    row = get_post_provider_settings()
    details = [
        ("ارائه‌دهنده", carrier_for(None).label),
        ("رهگیری خودکار", "ندارد" if not carrier_for(None).supports_tracking else "دارد"),
        ("حالت‌های تعریف‌شده", "، ".join(state.label for state in POSTAL_STATES)),
    ]
    if row.base_url:
        details.append(("نشانی پایهٔ سرویس", row.base_url))
    return details


def _unavailable_status(_user):
    return IntegrationStatus(
        state="unavailable",
        summary="در نسخه‌های بعدی افزوده می‌شود. هیچ تنظیمی برای آن وجود ندارد.",
    )


#: The table. One entry per service; adding one needs nothing else.
INTEGRATIONS = (
    Integration(
        key="sms",
        label="سامانهٔ پیامک",
        description="درگاه ارسال پیامک خروجی و دریافت پیامک ورودی.",
        icon="ki-sms",
        icon_paths=2,
        # `SmsProviderSettingsAccessMixin`'s own second gate, exactly:
        # feature (below), then Platform Admin.
        gate=lambda user: user.role == _platform_admin_role(),
        feature="outbound_sms",
        settings_url_name="common_ui:sms-provider-settings",
        test_url="/api/v1/sms-provider-settings/test/",
        status=_sms_status,
        details=_sms_details,
    ),
    Integration(
        key="post",
        label="سرویس پست",
        description="رهگیری وضعیت مرسوله‌ها و به‌روزرسانی خودکار مراحل ارسال.",
        icon="ki-truck",
        icon_paths=5,
        gate=lambda user: _has(user, "sales_documents.manage"),
        feature="sales_documents",
        settings_url_name="common_ui:post-provider-settings",
        test_url="/api/v1/post-provider-settings/test/",
        status=_post_status,
        details=_post_details,
    ),
    Integration(
        key="voip",
        label="تلفنی / VoIP",
        description=(
            "ثبت خودکار تماس‌ها، اتصال به سامانهٔ تلفن گویا یا مرکز تماس. "
            "دامنهٔ دقیق (فقط ثبت تماس، یا ضبط مکالمه، یا مرکز تماس کامل) و "
            "ارائه‌دهندهٔ هدف هنوز تعیین نشده‌اند."
        ),
        icon="ki-phone",
        icon_paths=2,
        status=_unavailable_status,
    ),
    Integration(
        key="coming_soon",
        label="سرویس‌های دیگر",
        description=(
            "درگاه پرداخت، سامانهٔ مؤدیان و سرویس‌های دیگری که بعداً اضافه "
            "می‌شوند، همین‌جا فهرست خواهند شد."
        ),
        icon="ki-abstract-26",
        icon_paths=2,
        status=_unavailable_status,
    ),
)


def any_integration_configurable(user):
    """Whether this reader may open *any* real integration's own settings —
    for the sidebar link into this page (product owner, 2026-09-21:
    «تنظیمات سامانهٔ پیامک باید به اتصال سامانه‌ها تغییر اسم یابد»), which
    has to decide this on every page load and therefore cannot afford
    `visible_integrations`'s own per-row status query (an outbound-SMS
    lookup, a post-settings row read) just to answer a yes/no.

    Feature and gate only, the same two checks `visible_integrations` makes
    before it ever calls a row's `status`, and skipping the placeholder row
    on purpose — it has neither a feature nor a gate and is always
    "visible", so counting it would make this always true regardless of
    what the reader can actually configure.
    """
    from common.deployment.profile import feature_enabled

    for integration in INTEGRATIONS:
        if not integration.settings_url_name:
            continue
        if integration.feature and not feature_enabled(integration.feature):
            continue
        if integration.gate and not integration.gate(user):
            continue
        return True
    return False


def visible_integrations(user):
    """The rows this reader may see, each with its status already resolved.

    A row is left out when its module is not licensed or the reader cannot
    configure it — a page listing services somebody can neither open nor
    change is a page that only raises questions. The placeholder has neither
    a feature nor a capability and is therefore always shown, which is the
    point of it.
    """
    from common.deployment.profile import feature_enabled

    rows = []
    for integration in INTEGRATIONS:
        if integration.feature and not feature_enabled(integration.feature):
            continue
        if integration.gate and not integration.gate(user):
            continue
        status = integration.status(user) if integration.status else IntegrationStatus(
            state="unavailable", summary=""
        )
        label, accent = STATE_LABELS.get(status.state, STATE_LABELS["unconfigured"])
        rows.append({
            "key": integration.key,
            "label": integration.label,
            "description": integration.description,
            "icon": integration.icon,
            "icon_paths": integration.icon_paths,
            "settings_url_name": integration.settings_url_name,
            "test_url": integration.test_url,
            "state": status.state,
            "state_label": label,
            "state_accent": accent,
            "summary": status.summary,
            "secret_hint": status.secret_hint,
            "last_error": status.last_error,
            "last_error_at": status.last_error_at,
            "details": integration.details(user) if integration.details else [],
        })
    return rows
