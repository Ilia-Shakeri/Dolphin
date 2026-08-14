from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count
from django.db.models.functions import ExtractHour, TruncDate

from communications.selectors import inbound_sms_for


REPORT_TIMEZONE = ZoneInfo(settings.TIME_ZONE)


def filtered_inbound_sms(
    *,
    actor,
    period_start,
    period_end,
    provider_code=None,
    recipient_normalized=None,
    processing_state=None,
):
    queryset = inbound_sms_for(actor).filter(
        provider_received_at__gte=period_start,
        provider_received_at__lt=period_end,
    )
    if provider_code:
        queryset = queryset.filter(provider_code=provider_code)
    if recipient_normalized:
        queryset = queryset.filter(recipient_normalized=recipient_normalized)
    if processing_state:
        queryset = queryset.filter(processing_state=processing_state)
    return queryset


def build_inbound_sms_report(**filters):
    queryset = filtered_inbound_sms(**filters)
    rows = list(
        queryset.annotate(
            local_date=TruncDate("provider_received_at", tzinfo=REPORT_TIMEZONE),
            local_hour=ExtractHour("provider_received_at", tzinfo=REPORT_TIMEZONE),
        )
        .values("local_date", "local_hour")
        .annotate(inbound_sms_count=Count("id"))
        .order_by("local_date", "local_hour")
    )
    return {
        "period_start": filters["period_start"].isoformat(),
        "period_end": filters["period_end"].isoformat(),
        "timezone": settings.TIME_ZONE,
        "filters": {
            key: filters.get(key)
            for key in ("provider_code", "recipient_normalized", "processing_state")
            if filters.get(key)
        },
        "total": sum(row["inbound_sms_count"] for row in rows),
        "results": rows,
    }


def inbound_sms_drilldown(*, local_date, local_hour, **filters):
    local_start = datetime.combine(local_date, time(hour=local_hour), tzinfo=REPORT_TIMEZONE)
    local_end = local_start + timedelta(hours=1)
    queryset = filtered_inbound_sms(**filters)
    return queryset.filter(
        provider_received_at__gte=local_start,
        provider_received_at__lt=local_end,
    ).order_by("-provider_received_at", "-id")

