from django.apps import AppConfig


class AccountingConfig(AppConfig):
    """The general-ledger app — see DOLPHIN_ACCOUNTING_PLAN.md.

    Phase 1 (manual double-entry posting + trial balance, nothing wired to
    any other module yet) — gated by the `accounting_ledger` feature flag
    in `common/deployment/registry.py`, default off, same as any other
    module a deployment must ask for.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounting"
    verbose_name = "حسابداری"
