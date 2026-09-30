"""PRELIMINARY, UNCOMMITTED — see integration/apps.py."""

from django.contrib import admin

from integration.models import OutboundEvent, PairingSettings


@admin.register(PairingSettings)
class PairingSettingsAdmin(admin.ModelAdmin):
    list_display = ("is_enabled", "updated_by", "updated_at")


@admin.register(OutboundEvent)
class OutboundEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "idempotency_key", "occurred_at", "dispatched_at", "attempts")
    list_filter = ("event_type", "dispatched_at")
    search_fields = ("idempotency_key",)
