from django.db.models import Q

from accounts.access import capabilities_for
from tasks.models import Task


def tasks_for(user):
    """Which tasks a person may see.

    `tasks.company` — every task. `tasks.own` — tasks assigned to them and
    tasks they created for someone else (so a manager-less creator can still
    follow up on what they handed out). Nothing otherwise.
    """
    capabilities = capabilities_for(user)
    if "tasks.company" in capabilities:
        return Task.objects.all()
    if "tasks.own" in capabilities:
        return Task.objects.filter(Q(assignee=user) | Q(created_by=user))
    return Task.objects.none()
