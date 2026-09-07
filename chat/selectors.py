"""Object scope for chat: a thread is visible only to its two participants.

Unlike every selector this codebase reuses (`attachments/selectors.py`
routes to a *parent's* own scope), chat has no parent record to defer to —
the scope rule is the thread's own membership, so it is defined here.
"""

from functools import reduce
from operator import or_

from django.db.models import Count, Max, Q

from chat.models import ChatMessage, ChatParticipant, ChatThread


def threads_for(user):
    """Every thread this user participates in, most recent activity first."""
    return ChatThread.objects.filter(participants__user=user).distinct()


def is_participant(user, thread_id):
    return ChatParticipant.objects.filter(thread_id=thread_id, user=user).exists()


def messages_for(user, thread_id):
    """Messages in one thread, or none if the user is not a participant.

    Object scope, not pagination — the view decides the page size and cursor.
    """
    if not is_participant(user, thread_id):
        return ChatMessage.objects.none()
    return ChatMessage.objects.filter(thread_id=thread_id).select_related("sender")


def unread_count_for(user, thread_id):
    """How many messages in this thread are newer than the user's own cursor.

    A participant who never opened the thread (`last_read_at` is null) has
    every message in it unread.
    """
    participant = ChatParticipant.objects.filter(thread_id=thread_id, user=user).first()
    if participant is None:
        return 0
    # A user's own messages are never counted against their own cursor — sent
    # is seen. `send_message` also advances the sender's own cursor for the
    # same reason; this exclusion is the defensive second check, matching how
    # this codebase already checks some rules at both the service and the
    # read side rather than trusting one alone.
    messages = ChatMessage.objects.filter(thread_id=thread_id).exclude(sender=user)
    if participant.last_read_at is not None:
        messages = messages.filter(created_at__gt=participant.last_read_at)
    return messages.count()


def last_messages_for(thread_ids):
    """The most recent message per thread, in two fixed queries.

    `ChatThreadListView` used to call `thread.messages.order_by(...).first()`
    once per thread in the list — one query per conversation the caller is
    in, on an endpoint the topbar polls every eight seconds regardless of
    whether the panel is even open. `Max("id")` groups every thread's rows in
    one query (message ids are already in send order, `Meta.ordering`), and
    the second fetches exactly those rows — two queries whether the caller
    has one thread or two hundred, not `2N`.
    """
    if not thread_ids:
        return {}
    latest_ids = (
        ChatMessage.objects.filter(thread_id__in=thread_ids)
        .values("thread_id")
        .annotate(last_id=Max("id"))
    )
    ids = [row["last_id"] for row in latest_ids]
    messages = ChatMessage.objects.filter(pk__in=ids)
    return {message.thread_id: message for message in messages}


def unread_counts_for(user, last_read_at_by_thread):
    """Unread counts for several threads at once, in one query.

    `last_read_at_by_thread` is `{thread_id: last_read_at_or_None}` for
    `user` — the caller already has this from the same `participants__user`
    prefetch it uses for the peer's name, so building it costs no extra
    query. Each thread's own cutoff becomes its own `Q`, and the `Q`s are
    OR'd into a single `WHERE`, grouped by thread — one query, not `2N`
    (`unread_count_for` above, called once per thread, was a lookup query
    *and* a count query each).
    """
    if not last_read_at_by_thread:
        return {}
    clauses = [
        Q(thread_id=thread_id) if last_read_at is None else Q(thread_id=thread_id, created_at__gt=last_read_at)
        for thread_id, last_read_at in last_read_at_by_thread.items()
    ]
    counts = (
        ChatMessage.objects.filter(reduce(or_, clauses))
        .exclude(sender=user)
        .values("thread_id")
        .annotate(count=Count("id"))
    )
    return {row["thread_id"]: row["count"] for row in counts}


def total_unread_count(user):
    """Unread messages across every thread this user is in — the topbar badge.

    Polled every few seconds on every open page (`setupChatUnreadPoll`), so
    the per-thread loop this used to run — a query to count each thread's
    unread messages, one thread at a time — was real, continuous load in
    proportion to how many conversations someone had accumulated. Reuses
    `unread_counts_for`'s single grouped query instead.
    """
    last_read_at_by_thread = dict(
        ChatParticipant.objects.filter(user=user).values_list("thread_id", "last_read_at")
    )
    return sum(unread_counts_for(user, last_read_at_by_thread).values())
