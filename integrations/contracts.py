"""What Dolphin needs from each outside system it does not connect to yet (2.40.45).

Roadmap priority 4: a payment gateway, the tax system (سامانهٔ مؤدیان), email,
the messengers (Bale, Telegram, WhatsApp) and a chat widget on the company's
own website. None of them is connected. Each waits for a real provider and its
official documentation — and the tax system also for a legal decision
(`CLAUDE.md` §31) — because what a provider actually requires is not something
to guess (`CLAUDE.md` §30).

What is fixed now is the seam. Each contract below is what a provider for that
kind of system implements, in the vocabulary Dolphin already uses. Connecting
one is then:

1. a provider module under `integrations/providers/` — its settings fields, its
   connection test, and this contract's methods — and one `register(...)`;
2. a feature in `common/deployment/registry.py`, off by default, that the
   provider names as `required_feature`;
3. the code that calls the contract where the work happens (recording a
   payment, sending an invoice, …), behind that feature;
4. its row leaving `common.integrations.UPCOMING_SERVICES`.

No page, table or API of the integrations framework changes. Until then the
«افزودن اتصال» catalog lists each one as «به‌زودی» with what it needs, and
offers nothing to press (`CLAUDE.md` §27). Nothing in the running panel calls
these contracts.

Every provider receives its stored settings the framework's way: `config`
(plain values) and `secrets` (decrypted credentials), never read from anywhere
else, and never logged or returned to the browser.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


# --- results every contract returns -------------------------------------------

@dataclass(frozen=True)
class DeliveryResult:
    """One message handed to an outside system: whether it took it, its id."""

    accepted: bool
    provider_message_id: str = ""
    message: str = ""


@dataclass(frozen=True)
class InboundMessage:
    """One message an outside system delivered to Dolphin."""

    sender: str
    text: str
    received_at: datetime
    provider_message_id: str = ""


@dataclass(frozen=True)
class PaymentRedirect:
    """Where to send the payer, and the gateway's reference for this attempt."""

    redirect_url: str
    reference: str


@dataclass(frozen=True)
class PaymentVerification:
    """The gateway's own answer, from its server, on whether money moved."""

    paid: bool
    amount_rial: Decimal
    provider_reference: str = ""
    message: str = ""


@dataclass(frozen=True)
class TaxSubmission:
    """Where one invoice stands at the tax system."""

    status: str
    tax_id: str = ""
    message: str = ""
    details: dict = field(default_factory=dict)


# --- the contracts --------------------------------------------------------------

class PaymentGateway(ABC):
    """An online payment for an invoice (`payment_gateway`).

    Dolphin starts the payment and later asks the gateway itself whether it
    succeeded; a payment is recorded only on `verify`'s answer from the
    gateway's server, never on the payer's browser returning to Dolphin, and a
    second `verify` of the same reference must not record it twice. Amounts are
    whole rial, as Dolphin stores them. How the recorded payment is allocated to
    the invoice stays `billing.services`'.
    """

    capability = "payment"

    @abstractmethod
    def start(self, *, config, secrets, invoice_number, amount_rial, callback_url, description) -> PaymentRedirect:
        """Open a payment for `amount_rial` and say where to send the payer."""

    @abstractmethod
    def verify(self, *, config, secrets, reference, callback_params) -> PaymentVerification:
        """Ask the gateway, server to server, whether `reference` was paid."""


class TaxSystemClient(ABC):
    """Sending official invoices to the tax system, سامانهٔ مؤدیان (`tax_system`).

    Which invoices are sent, when, and how a cancellation or a correction is
    reported are legal decisions not yet taken (`CLAUDE.md` §31); this fixes
    only that an invoice is submitted and its standing can be asked for again.
    """

    capability = "tax"

    @abstractmethod
    def submit(self, *, config, secrets, invoice) -> TaxSubmission:
        """Send one issued official invoice."""

    @abstractmethod
    def status(self, *, config, secrets, tax_id) -> TaxSubmission:
        """Where a submitted invoice stands now."""


class EmailSender(ABC):
    """Email to customers and users — an invoice's PDF, a notification (`email`)."""

    capability = "email"

    @abstractmethod
    def send(self, *, config, secrets, to, subject, text, html=None, attachments=()) -> DeliveryResult:
        """Send one message. `attachments` holds `(filename, bytes, content_type)`."""


class MessengerChannel(ABC):
    """A messenger bot — Bale, Telegram, WhatsApp — with its own provider (`messengers`).

    Inbound messages already reach Dolphin through the generic webhook
    connection (`integrations.providers.generic`); a messenger provider adds
    replying, and reads the messenger's own payload rather than a generic one.
    """

    capability = "messaging"

    @abstractmethod
    def send(self, *, config, secrets, recipient, text) -> DeliveryResult:
        """Send `text` to one chat or number."""

    @abstractmethod
    def parse_inbound(self, *, config, payload) -> list[InboundMessage]:
        """The messages in one verified inbound payload."""


class SiteChatChannel(ABC):
    """A chat box on the company's own website whose conversations land in
    Dolphin (`site_chat`) — a hosted widget's provider, or Dolphin's own.

    Who a visitor is, and how a conversation becomes a customer or a lead, are
    product decisions still to be made.
    """

    capability = "site_chat"

    @abstractmethod
    def widget_snippet(self, *, config) -> str:
        """The code the company puts on its website to show the chat box."""

    @abstractmethod
    def parse_inbound(self, *, config, payload) -> list[InboundMessage]:
        """The visitor messages in one verified inbound payload."""

    @abstractmethod
    def reply(self, *, config, secrets, conversation, text) -> DeliveryResult:
        """Answer one visitor conversation."""


#: Each upcoming service, by its catalog key, and the contract its provider implements.
CONTRACTS = {
    "payment_gateway": PaymentGateway,
    "tax_system": TaxSystemClient,
    "email": EmailSender,
    "messengers": MessengerChannel,
    "site_chat": SiteChatChannel,
}
