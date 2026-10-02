"""Backfill for customer ownership and structured categories (2.35.0).

One implementation shared by the migration and by the
`backfill_customer_ownership` command (which adds `--dry-run`). It takes the
model classes as arguments so the migration can pass its historical models.

Expand-only and idempotent:

* `owner` is set to `created_by` only where it is still empty.
* A `CustomerCategory` is created per distinct *normalised* category text, and
  `category_ref` is set only where it is still empty. The text column is never
  touched, so every old reader keeps working and a rollback loses nothing.
* Two spellings that differ only by spacing or a half-space (ZWNJ) are **not**
  merged; they become separate categories and are listed in the report for a
  person to decide.
"""

import unicodedata
from dataclasses import dataclass, field

_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_INVISIBLE = dict.fromkeys(map(ord, "​‍﻿"))


def normalize_label(value):
    """The key a category is unique by: one spelling per visible text."""
    text = unicodedata.normalize("NFKC", str(value or "")).translate(_LETTERS).translate(_DIGITS)
    text = text.translate(_INVISIBLE)
    return " ".join(text.split()).casefold()


def loose_key(value):
    """Spacing and half-spaces ignored: the 'probably the same' test."""
    return normalize_label(value).replace("‌", "").replace(" ", "")


def clean_label(value):
    """The label as displayed: whitespace tidied, letters unified."""
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).translate(_LETTERS).translate(_INVISIBLE).split())


@dataclass
class BackfillReport:
    owners_to_fill: int = 0
    categories_to_create: int = 0
    customers_to_link: int = 0
    ambiguous: list = field(default_factory=list)

    def as_lines(self):
        lines = [
            f"owner to fill: {self.owners_to_fill}",
            f"categories to create: {self.categories_to_create}",
            f"customers to link to a category: {self.customers_to_link}",
            f"ambiguous category groups (need review): {len(self.ambiguous)}",
        ]
        lines += [f"  - {' | '.join(group)}" for group in self.ambiguous]
        return lines


def run_backfill(Customer, CustomerCategory, *, apply):
    report = BackfillReport()
    pending_owner = Customer.objects.filter(owner__isnull=True)
    report.owners_to_fill = pending_owner.count()
    if apply:
        for customer in pending_owner.iterator():
            Customer.objects.filter(pk=customer.pk, owner__isnull=True).update(owner_id=customer.created_by_id)

    existing = {c.normalized_name: c for c in CustomerCategory.objects.all()}
    # normalised text -> (display label, first customer's creator)
    wanted = {}
    for customer in Customer.objects.filter(category_ref__isnull=True).exclude(category="").only("category", "created_by_id").order_by("id").iterator():
        key = normalize_label(customer.category)
        if key and key not in wanted:
            wanted[key] = (clean_label(customer.category), customer.created_by_id)
    groups = {}
    for key, (label, _creator) in wanted.items():
        groups.setdefault(loose_key(label), []).append(label)
    for labels in groups.values():
        if len(labels) > 1:
            report.ambiguous.append(sorted(labels))
    for key, (label, creator) in wanted.items():
        if key in existing:
            continue
        report.categories_to_create += 1
        if apply:
            existing[key] = CustomerCategory.objects.create(
                name=label[:100], normalized_name=key[:100], created_by_id=creator, updated_by_id=creator,
            )
    for customer in Customer.objects.filter(category_ref__isnull=True).exclude(category="").only("category").iterator():
        key = normalize_label(customer.category)
        if key not in existing and not apply:
            report.customers_to_link += 1
            continue
        if key in existing:
            report.customers_to_link += 1
            if apply:
                Customer.objects.filter(pk=customer.pk, category_ref__isnull=True).update(category_ref_id=existing[key].pk)
    return report
