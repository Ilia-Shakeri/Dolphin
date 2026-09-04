"""Object scope for chat: a thread is visible only to its two participants.

Unlike every selector this codebase reuses (`attachments/selectors.py`
routes to a *parent's* own scope), chat has no parent record to defer to —
the scope rule is the thread's own membership, so it is defined here.
"""

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


def total_unread_count(user):
    """Unread messages across every thread this user is in — the topbar badge."""
    total = 0
    for participant in ChatParticipant.objects.filter(user=user).select_related("thread"):
        messages = ChatMessage.objects.filter(thread_id=participant.thread_id).exclude(sender=user)
        if participant.last_read_at is not None:
            messages = messages.filter(created_at__gt=participant.last_read_at)
        total += messages.count()
    return total
