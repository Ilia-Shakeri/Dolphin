"""«حقیقی» / «حقوقی» with their icon, the one way the panel shows a customer's kind (2.40.8).

The labels are `sales.models.Customer.Kind`'s own; the icons are the UI kit's:
a person for an individual, a building for a legal entity. The icon is `1em`
in `currentColor` (`.customer-kind` in dolphin.css), so it always matches the
text beside it, and it is `aria-hidden` — the word is already there. The
JavaScript twin is `ui/customer-kind.js`; Excel exports keep plain words.
"""

from django import template
from django.utils.html import format_html, format_html_join

register = template.Library()

#: kind -> (icon, number of duotone paths). The JS twin holds the same table.
ICONS = {"individual": ("di-profile-circle", 3), "legal": ("di-bank", 2)}


def _label(kind):
    from sales.models import Customer

    return dict(Customer.Kind.choices).get(kind, "")


@register.simple_tag
def customer_kind_label(kind):
    """The plain word, for a place an icon cannot go (a native `<option>`)."""
    return _label(kind)


@register.simple_tag
def customer_kind(kind):
    label = _label(kind)
    if not label:
        return ""
    icon, paths = ICONS[kind]
    spans = format_html_join("", '<span class="path{}"></span>', ((n,) for n in range(1, paths + 1)))
    return format_html(
        '<span class="customer-kind" data-customer-kind-badge="{}"><i class="di-duotone {} customer-kind-icon" aria-hidden="true">{}</i><span>{}</span></span>',
        kind, icon, spans, label,
    )
