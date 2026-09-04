"""Internal one-to-one chat between two users of the same deployment.

Product-owner request (2026-09-04): a chat *inside the panel*, for
coordination between colleagues (a sales agent and their manager on a
specific lead, for instance) — not a replacement for a real messaging
product, and not a customer-facing channel. Scope is deliberately narrow for
this first cut: a direct (exactly two-participant) thread only. Group chat is
visible in the purchased theme's own demo (`apps/chat/group.html`) but was
not asked for here and is not built — a later, separate decision, same as
`docs/backend/OPEN_BUSINESS_DECISIONS.md` treats every other not-yet-decided
scope.

Three models, the same shape `attachments` used: a real typed foreign key
for every relationship (no `GenericForeignKey`), `PROTECT` everywhere a row
is never deleted by this app (there is no delete operation here — a message,
once sent, stays, matching the panel's "audit trail, not a diary you can
edit" convention elsewhere — Sale correction, invoice reissue, activity log).

Read state lives on `ChatParticipant.last_read_at` rather than a flag per
message, because "read" is a per-viewer cursor over the whole thread, not a
property of any one message — the same reason `AfterSalesRequest` tracks a
single `next_appointment_at` rather than a read flag per historical event.
"""

from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel


class ChatThread(TimeStampedModel):
    """A direct conversation between exactly two users.

    Nothing on this row names the two participants — `ChatParticipant` does,
    the same way `Payment`/`PaymentAllocation` keeps the relationship in its
    own row rather than a pair of nullable columns here. "Exactly two" for a
    direct thread is enforced in `chat/services.py`
    (`get_or_create_direct_thread`), not by a database constraint: Postgres
    has no `CHECK` that counts rows in a *related* table, and a trigger for
    this one invariant would be more moving parts than the service-layer lock
    already used for every other "exactly one/exactly two" rule in this
    codebase (`attachments.Attachment`'s five-nullable-FK constraint is a
    single row's own columns, which is why that one *is* a `CheckConstraint`
    and this is not).
    """

    #: Denormalised copy of the latest message's `created_at`, kept here so
    #: "my threads, most recent activity first" is one indexed `ORDER BY` on
    #: this table instead of a `MAX(created_at)` aggregate over every
    #: thread's messages on every request. Written by
    #: `chat/services.py:send_message`, nowhere else.
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]


class ChatParticipant(TimeStampedModel):
    """One user's membership in one thread, and their own read cursor."""

    thread = models.ForeignKey(ChatThread, on_delete=models.PROTECT, related_name="participants")
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="chat_participations")
    #: Every message with `created_at <= last_read_at` is read, for this user
    #: only. Null means "never opened this thread" — every message unread —
    #: rather than a sentinel timestamp, so a thread with zero messages read
    #: is indistinguishable from one that does not exist yet, not from one
    #: read a very long time ago.
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["thread", "user"], name="chat_participant_unique_per_thread"),
        ]
        indexes = [
            models.Index(fields=["user", "thread"]),
        ]


class ChatMessage(TimeStampedModel):
    """One sent message. Immutable — this app has no edit or delete."""

    thread = models.ForeignKey(ChatThread, on_delete=models.PROTECT, related_name="messages")
    sender = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    body = models.CharField(max_length=4000)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(body__regex=r"\S"), name="chat_message_body_nonblank"),
        ]
        indexes = [
            models.Index(fields=["thread", "created_at"]),
        ]
