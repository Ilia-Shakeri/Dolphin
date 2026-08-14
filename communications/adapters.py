from typing import Any, Mapping, Protocol

from communications.services import NormalizedInboundSMSEvent


class InboundSMSProviderAdapter(Protocol):
    """Provider adapter boundary. No provider implementation is active."""

    provider_code: str

    def authenticate_and_normalize(
        self,
        *,
        headers: Mapping[str, str],
        payload: bytes,
    ) -> NormalizedInboundSMSEvent:
        """Verify provider proof and return one normalized event."""

    def replay_context(self, *, headers: Mapping[str, str]) -> Mapping[str, Any]:
        """Return bounded replay facts after provider authentication."""

