"""PRELIMINARY, UNCOMMITTED — see integration/apps.py."""

from django.urls import path

from integration.views import HandoffMintView, PairingSettingsView

app_name = "integration_api"

urlpatterns = [
    path("integration/pairing/", PairingSettingsView.as_view(), name="pairing-settings"),
    path("integration/handoff/mint/", HandoffMintView.as_view(), name="handoff-mint"),
]
