"""PRELIMINARY, UNCOMMITTED — see integration/apps.py."""

from rest_framework import serializers


class PairingSettingsSerializer(serializers.Serializer):
    is_enabled = serializers.BooleanField()
    has_shared_secret = serializers.BooleanField()


class PairingSettingsUpdateSerializer(serializers.Serializer):
    is_enabled = serializers.BooleanField(required=False)
    shared_secret = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class HandoffMintResponseSerializer(serializers.Serializer):
    url = serializers.CharField()
