"""Every activity row names a role (owner decision 2026-10-14, BIZ-012).

Rows written before 2.x recorded roles have an empty `actor_role_snapshot`.
They are filled in here: with the actor's role as it is now, or `system` for a
row with no actor (only commands and scheduled jobs write those; an actor can
never be deleted out from under a row, the foreign key protects it). Either
way the row is marked `actor_role_inferred`, so the page can say the role is
today's rather than the one held when it happened.

Reversible: going back empties exactly the rows this filled and drops the
column. The application's database role has no UPDATE on this table; this runs
as the migration owner, like every migration.
"""

from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def fill_roles(apps, schema_editor):
    ActivityLog = apps.get_model("auditlog", "ActivityLog")
    User = apps.get_model("accounts", "User")
    ActivityLog.objects.filter(actor_role_snapshot="", actor__isnull=False).update(
        actor_role_snapshot=Subquery(User.objects.filter(pk=OuterRef("actor_id")).values("role")[:1]),
        actor_role_inferred=True,
    )
    ActivityLog.objects.filter(actor_role_snapshot="", actor__isnull=True).update(
        actor_role_snapshot="system",
        actor_role_inferred=True,
    )


def empty_filled_roles(apps, schema_editor):
    ActivityLog = apps.get_model("auditlog", "ActivityLog")
    ActivityLog.objects.filter(actor_role_inferred=True).update(actor_role_snapshot="", actor_role_inferred=False)


class Migration(migrations.Migration):
    dependencies = [
        ("auditlog", "0002_activitylog_role_snapshots"),
        ("accounts", "0009_two_factor"),
    ]

    operations = [
        migrations.AddField(
            model_name="activitylog",
            name="actor_role_inferred",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(fill_roles, empty_filled_roles),
    ]
