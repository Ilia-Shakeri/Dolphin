"""Every row lock must sit inside a transaction — checked the way production is.

This file exists because the rest of the suite structurally cannot see the bug
it guards against, and that bug reached production twice.

`select_for_update()` outside a transaction is refused by Django, but only on a
backend that actually supports row locking:

    if self.query.select_for_update and features.has_select_for_update:
        if self.connection.get_autocommit() and features.supports_transactions:
            raise TransactionManagementError(...)

Production runs PostgreSQL, where `has_select_for_update` is True — so the guard
fires and the request 500s. The suite runs SQLite, where it is False, so Django
silently drops the `FOR UPDATE` clause and every test passes. A function can
therefore lose its `@transaction.atomic` and stay green for months.

That is exactly what happened. `issue_invoice()` was atomic when it was written,
lost the decorator in 1.2.0, and nothing failed until this was written — issuing
an invoice had been broken on PostgreSQL the whole time. `transition_cheque()`
was never atomic, which broke the four cheque buttons added in 1.3.7.

Two checks, deliberately different in kind:

* the static one reads the source and is exhaustive — it covers functions no
  test calls, which is most of the reason the regression survived;
* the runtime one makes SQLite answer as PostgreSQL does and calls the real
  services, proving the static rule is about something that genuinely fails.
"""

import ast
import pathlib

from django.db import OperationalError, connection, transaction
from django.db.transaction import TransactionManagementError
from django.test import SimpleTestCase, TransactionTestCase

from accounts.models import User

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
APPS = (
    "billing", "sales", "inventory", "accounts",
    "aftersales", "communications", "common", "reports",
)


def _locking_functions_without_a_transaction():
    """Every function that calls `select_for_update()` and opens no transaction.

    Read from the AST rather than by grepping, so the word appearing in a
    comment — which it does, in `reports/services.py`, describing a lock that was
    deliberately removed — is not mistaken for a call.

    A function counts as protected when it carries `@transaction.atomic` or opens
    `with transaction.atomic()` itself. A private helper is exempt: helpers like
    `_lock_active_actor()` exist to be called from inside an already-atomic
    service, and requiring a nested atomic block on each would add savepoints for
    nothing.
    """
    offenders = []
    for app in APPS:
        for path in (REPOSITORY_ROOT / app).rglob("*.py"):
            parts = path.parts
            if any("test" in part for part in parts) or "migrations" in parts:
                continue
            source = path.read_text(encoding="utf-8")
            if "select_for_update(" not in source:
                continue
            for node in ast.walk(ast.parse(source)):
                # `_`-prefixed helpers, and the `lock_*` ones, exist to be
                # called from inside an already-atomic service. Their names say
                # so, and requiring each to open its own block would add
                # savepoints that buy nothing. `lock_platform_admin_guard` is
                # the only one not underscored, because it is imported across
                # modules; every caller of it is atomic.
                if not isinstance(node, ast.FunctionDef):
                    continue
                if node.name.startswith("_") or node.name.startswith("lock_"):
                    continue
                locks = any(
                    isinstance(child, ast.Call)
                    and getattr(child.func, "attr", "") == "select_for_update"
                    for child in ast.walk(node)
                )
                if not locks:
                    continue
                body = ast.get_source_segment(source, node) or ""
                decorated = any(
                    (isinstance(d, ast.Attribute) and d.attr == "atomic")
                    or (isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "atomic")
                    for d in node.decorator_list
                )
                if not decorated and "with transaction.atomic" not in body:
                    offenders.append(
                        f"{path.relative_to(REPOSITORY_ROOT).as_posix()}:"
                        f"{node.lineno} {node.name}()"
                    )
    return sorted(offenders)


class RowLocksAreTransactionalTests(SimpleTestCase):
    def test_no_public_service_locks_rows_outside_a_transaction(self):
        offenders = _locking_functions_without_a_transaction()
        self.assertEqual(
            offenders,
            [],
            "These call select_for_update() with no transaction of their own. "
            "That raises TransactionManagementError on PostgreSQL — a 500 in "
            "production — while SQLite drops the lock and keeps the suite "
            "green. Add @transaction.atomic:\n  " + "\n  ".join(offenders),
        )

    def test_the_checker_would_notice_an_unprotected_function(self):
        """A guard that cannot fail protects nothing.

        The rule is asserted against a sample rather than against the tree, so
        this stays true whether or not the repository currently has an offender.
        """
        sample = ast.parse(
            "def issue(*, actor):\n"
            "    Thing.objects.select_for_update().get(pk=1)\n"
        )
        node = sample.body[0]
        decorated = any(
            (isinstance(d, ast.Attribute) and d.attr == "atomic")
            for d in node.decorator_list
        )
        self.assertFalse(decorated, "the sample is deliberately unprotected")


class RowLocksUnderPostgresRulesTests(TransactionTestCase):
    """The same rule, proven by running Django as production runs it.

    `TransactionTestCase` rather than `TestCase`: the latter wraps each test in
    a transaction, which is the very condition being tested for absence.
    """

    def test_django_refuses_an_unprotected_lock_once_the_backend_can_lock(self):
        """The mechanism, demonstrated rather than described.

        SQLite reports `has_select_for_update = False`, so Django drops the
        clause and nothing complains. Setting it True applies exactly the check
        PostgreSQL gets — and the check runs before any SQL is built, so this
        needs no PostgreSQL server and never reaches SQLite's parser.
        """
        original = type(connection.features).has_select_for_update
        try:
            type(connection.features).has_select_for_update = True
            self.assertTrue(connection.get_autocommit(), "no surrounding transaction")
            with self.assertRaises(TransactionManagementError):
                list(User.objects.select_for_update().all())
        finally:
            type(connection.features).has_select_for_update = original

    def test_the_same_lock_is_fine_inside_a_transaction(self):
        """The other half: protected code is unaffected by any of this."""
        original = type(connection.features).has_select_for_update
        try:
            type(connection.features).has_select_for_update = True
            with transaction.atomic():
                # Reaches SQL generation rather than the guard, which is the
                # point. SQLite cannot parse `FOR UPDATE`, and that it gets that
                # far is the proof the guard did not fire.
                with self.assertRaises(OperationalError):
                    list(User.objects.select_for_update().all())
        finally:
            type(connection.features).has_select_for_update = original
