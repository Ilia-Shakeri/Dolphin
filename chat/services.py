"""Starting a thread and sending a message — the only two state changes here.

Reading (thread list, message list, unread counts) needs no service function:
object scope alone (`chat/selectors.py`) decides what a request may see,
exactly like `attachments`. Only a write needs the actor lock and an audit
log entry.

No role or capability check gates any of this beyond "is a real, active,
ordinary CRM identity" (`is_crm_identity`) — chat is cross-role coordination
by design (a sales agent messaging their manager, or an after-sales operator
messaging platform admin about one case), not a module scoped to a workstream
or a capability the way `customers.manage`/`leads.manage` are. The feature
gate (`internal_chat` in `common/deployment/registry.py`) is the only switch:
off, the whole module is a 404; on, every ordinary role may use it.
"""

from django.db import transaction
from django.utils import timezone

from accounts.access import is_crm_identity
from accounts.models import User
from auditlog.services import log_activity
from chat.models import ChatMessage, ChatParticipant, ChatThread
from common.exceptions import BusinessPermissionDenied, BusinessRuleError

MESSAGE_MAX_LENGTH = 4000


def _lock_active_actor(actor):
    locked = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if locked is None or not is_crm_identity(locked):
        raise BusinessPermissionDenied("کاربر باید فعال باشد.")
    return locked


def _clean_body(value):
    cleaned = str(value or "").strip()
    if not cleaned:
        raise BusinessRuleError({"body": "متن پیام نمی‌تواند خالی باشد."})
    if len(cleaned) > MESSAGE_MAX_LENGTH:
        raise BusinessRuleError({"body": f"متن پیام نباید بیش از {MESSAGE_MAX_LENGTH} نویسه باشد."})
    return cleaned


@transaction.atomic
def get_or_create_direct_thread(*, actor, other_user_id):
    """The one thread between `actor` and `other_user_id`, creating it if needed.

    Idempotent by design: calling this twice for the same pair returns the
    same row both times, found by intersecting each user's own participant
    set rather than a `(user_a, user_b)` unique column — a column would need
    a canonical ordering (`min(id), max(id)`) to stay unique regardless of
    which side started the thread; the intersection needs none.
    """
    locked_actor = _lock_active_actor(actor)
    if other_user_id == locked_actor.pk:
        raise BusinessRuleError({"other_user_id": "نمی‌توانید با خودتان گفت‌وگو شروع کنید."})
    other_user = User.objects.filter(pk=other_user_id).first()
    if not is_crm_identity(other_user):
        raise BusinessRuleError({"other_user_id": "کاربر مقصد پیدا نشد."})

    existing = (
        ChatThread.objects.filter(participants__user=locked_actor)
        .filter(participants__user_id=other_user_id)
        .first()
    )
    if existing is not None:
        return existing

    thread = ChatThread.objects.create()
    ChatParticipant.objects.create(thread=thread, user=locked_actor)
    ChatParticipant.objects.create(thread=thread, user=other_user)
    log_activity(
        actor=locked_actor,
        operation="chat_thread.started",
        instance=thread,
        changes={"with_user_id": other_user_id},
    )
    return thread


@transaction.atomic
def send_message(*, actor, thread_id, body):
    locked_actor = _lock_active_actor(actor)
    participant = ChatParticipant.objects.select_for_update().filter(
        thread_id=thread_id, user=locked_actor
    ).first()
    if participant is None:
        raise BusinessPermissionDenied("شما عضو این گفت‌وگو نیستید.")
    cleaned = _clean_body(body)

    now = timezone.now()
    message = ChatMessage.objects.create(thread_id=thread_id, sender=locked_actor, body=cleaned)
    # Sent is seen, for the sender's own cursor — see chat/selectors.py's own
    # note on why unread counting also excludes a user's own messages.
    participant.last_read_at = now
    participant.save(update_fields=["last_read_at", "updated_at"])
    ChatThread.objects.filter(pk=thread_id).update(last_message_at=message.created_at)
    log_activity(
        actor=locked_actor,
        operation="chat_message.sent",
        instance=message,
        changes={"thread_id": thread_id},
    )
    return message


@transaction.atomic
def mark_thread_read(*, actor, thread_id):
    locked_actor = _lock_active_actor(actor)
    participant = ChatParticipant.objects.select_for_update().filter(
        thread_id=thread_id, user=locked_actor
    ).first()
    if participant is None:
        raise BusinessPermissionDenied("شما عضو این گفت‌وگو نیستید.")
    participant.last_read_at = timezone.now()
    participant.save(update_fields=["last_read_at", "updated_at"])
    return participant
