"""PRELIMINARY, UNCOMMITTED — cross-product integration with Dolphin
Accounting, proposed 2026-09-08 alongside that product's own first version.
See this session's report to the product owner before committing anything
here: not yet reviewed, not yet decided as final.
"""

from django.apps import AppConfig


class IntegrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integration"
    verbose_name = "اتصال به دلفین حسابداری"
