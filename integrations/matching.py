"""Who is this number? — contact matching for every integration (2.21.0).

A caller ID, an SMS sender or a messenger handle arrives as a string; this
turns it into the Dolphin people it belongs to. In order:

1. an active customer phone with exactly that normalized number;
2. a colleague (`User.normalized_phone`);
3. leniently, the last ten digits — PBX trunks deliver `+98912…`, `0912…`,
   `912…` or an operator-prefixed `90912…` for the same person;
4. the number a logged call was made to (`Interaction.normalized_phone`),
   pointing at that call's customer.

Matching is a system-level lookup and ignores who is asking: a caller is
matched to the right person whatever the screen they land on. What a given
reader may *see* of that person is decided where the match is shown.
"""

import re
from dataclasses import dataclass

from common.phones import normalized_or_blank

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


@dataclass(frozen=True)
class Match:
    person_type: str
    person_id: int
    name: str
    #: How it was found: `exact`, `suffix` or `history`.
    how: str


def digits_only(raw):
    return re.sub(r"\D", "", str(raw or "").translate(_DIGITS))


def normalize_caller(raw):
    """E.164 for anything that is an Iranian number, allowing for the
    shapes PBXs send (`98912…`, `00989…`, `0912…`, `912…`)."""
    value = normalized_or_blank(raw)
    if value:
        return value
    digits = digits_only(raw)
    if len(digits) > 10:
        return normalized_or_blank(digits[-10:])
    return ""


def match_phone(raw, *, limit=5):
    """Every person this number belongs to, best first (possibly empty)."""
    from accounts.access import crm_identities
    from accounts.models import User
    from sales.models import CustomerPhone, Interaction

    normalized = normalize_caller(raw)
    if not normalized:
        return []
    found, seen = [], set()

    def add(person_type, person_id, name, how):
        key = (person_type, person_id)
        if key not in seen:
            seen.add(key)
            found.append(Match(person_type, person_id, name, how))

    for phone in (
        CustomerPhone.objects.filter(normalized_phone=normalized, is_active=True, customer__is_active=True)
        .select_related("customer")[:limit]
    ):
        add("customer", phone.customer_id, phone.customer.full_name, "exact")
    for user in crm_identities(User.objects.filter(normalized_phone=normalized, is_active=True))[:limit]:
        add("user", user.pk, user.get_full_name() or user.username, "exact")
    if not found:
        suffix = normalized[-10:]
        for phone in (
            CustomerPhone.objects.filter(normalized_phone__endswith=suffix, is_active=True, customer__is_active=True)
            .select_related("customer")[:limit]
        ):
            add("customer", phone.customer_id, phone.customer.full_name, "suffix")
    if not found:
        for interaction in (
            Interaction.objects.filter(normalized_phone=normalized)
            .select_related("customer", "lead__customer")
            .order_by("-occurred_at")[:limit]
        ):
            customer = interaction.customer or (interaction.lead.customer if interaction.lead_id else None)
            if customer is not None and customer.is_active:
                add("customer", customer.pk, customer.full_name, "history")
    return found[:limit]


def best_match(raw):
    matches = match_phone(raw, limit=1)
    return matches[0] if matches else None


def match_email(raw):
    from accounts.access import crm_identities
    from accounts.models import User
    from sales.models import Customer

    email = str(raw or "").strip().lower()
    if not email or "@" not in email:
        return []
    found = [
        Match("customer", customer.pk, customer.full_name, "exact")
        for customer in Customer.objects.filter(email__iexact=email, is_active=True)[:5]
    ]
    found += [
        Match("user", user.pk, user.get_full_name() or user.username, "exact")
        for user in crm_identities(User.objects.filter(email__iexact=email, is_active=True))[:5]
    ]
    return found
