"""A person's score and the weights that produce it (2.20.0).

The score is **rule-based and explainable**: each factor contributes points
for a stated reason, and the breakdown is stored with every snapshot so a
reader can always see why a number is what it is. Weights have defaults in
code (`scoring.strategies`, decision D21) and a Platform Admin may change
them here; nothing about how a factor is *measured* is configurable, only how
much it counts.
"""

from django.conf import settings
from django.db import models


class ScoringSettings(models.Model):
    """One deployment's own weights — blank means "the defaults in code"."""

    SINGLETON = 1

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON)
    #: `{factor key: weight}`; a factor missing here uses its default.
    customer_weights = models.JSONField(default=dict, blank=True)
    user_weights = models.JSONField(default=dict, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "scoring settings"
        verbose_name_plural = "scoring settings"
        constraints = [
            models.CheckConstraint(condition=models.Q(singleton=1), name="scoring_settings_is_singleton"),
        ]


class PersonScore(models.Model):
    """One computed score — the newest row is the current score, the rest
    are its history."""

    person_type = models.CharField(max_length=32)
    person_id = models.PositiveBigIntegerField()
    score = models.PositiveSmallIntegerField()
    level = models.CharField(max_length=20)
    #: `[{key, label, weight, points, applicable, reason}, …]` — the whole
    #: explanation, frozen with the number it explains.
    breakdown = models.JSONField(default=list)
    strategy = models.CharField(max_length=40)
    computed_at = models.DateTimeField()

    class Meta:
        verbose_name = "person score"
        verbose_name_plural = "person scores"
        indexes = [
            models.Index(fields=["person_type", "person_id", "-computed_at"], name="person_score_recent"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(score__lte=100), name="person_score_at_most_100"),
            models.CheckConstraint(
                condition=models.Q(level__in=["excellent", "good", "fair", "weak"]), name="person_score_level_valid"
            ),
        ]
