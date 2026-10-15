"""What the assistant may read about one customer (2.40.55).

Everything comes through the owning modules' own scoped selectors
(`customers_for`, `leads_for`, `interactions_for`, `invoices_for`,
`after_sales_requests_for`), each gated by its own feature: the model is
never shown a record the person asking could not open themselves (owner
decision 2026-10-14: «در محدودهٔ دسترسی کاربر»). The text is bounded, and it
is handed to the model as data, never as instructions.
"""

from django.db.models import Q, Sum

from common.deployment.profile import feature_enabled
from common.jalali import format_date, format_datetime

MAX_CHARS = 6000
NOTE_CHARS = 300


def _line(label, value):
    value = " ".join(str(value or "").split())
    return f"- {label}: {value}" if value else ""


def customer_context(user, customer):
    """A plain Persian outline of the customer, as far as `user` may see it."""
    lines = ["# مشتری", _line("نام", customer.full_name), _line("نوع", customer.get_kind_display()),
             _line("سمت", customer.job_title), _line("استان و شهر", "، ".join(filter(None, [customer.province, customer.city]))),
             _line("دسته‌بندی", customer.category), _line("تاریخ ثبت", format_date(customer.created_at))]
    from customization.services import definitions_for, display_value

    for item in definitions_for("customer"):
        lines.append(_line(item.label, display_value(item, (customer.custom_fields or {}).get(item.key, ""))))

    if feature_enabled("leads"):
        from sales.selectors import interactions_for, leads_for

        leads = list(
            leads_for(user).filter(customer=customer).select_related("interested_product").order_by("-updated_at")[:5]
        )
        if leads:
            lines.append("\n# سرنخ‌ها")
            for lead in leads:
                lines.append(
                    f"- وضعیت {lead.get_status_display() or 'نامشخص'}"
                    + (f"، منبع {lead.source}" if lead.source else "")
                    + (f"، علاقه به {lead.interested_product.name}" if lead.interested_product_id else "")
                    + (f"، پیگیری بعدی {format_datetime(lead.next_follow_up_at)}" if lead.next_follow_up_at else "")
                )
        calls = list(
            interactions_for(user).filter(Q(customer=customer) | Q(lead__customer=customer)).order_by("-occurred_at")[:8]
        )
        if calls:
            lines.append("\n# آخرین تماس‌ها")
            for call in calls:
                note = " ".join((call.notes or "").split())[:NOTE_CHARS]
                lines.append(f"- {format_datetime(call.occurred_at)}، {call.get_direction_display()}، نتیجه: {call.outcome}" + (f"، یادداشت: {note}" if note else ""))

    if feature_enabled("invoices"):
        from billing.selectors import invoices_for

        issued = invoices_for(user).filter(customer=customer, status="issued")
        totals = issued.aggregate(total=Sum("total_amount"), paid=Sum("paid_amount"))
        count = issued.count()
        if count:
            total = int(totals["total"] or 0)
            owed = int((totals["total"] or 0) - (totals["paid"] or 0))
            lines.append("\n# خرید و حساب")
            lines.append(f"- {count} فاکتور صادرشده به جمع {total:,} ریال؛ ماندهٔ پرداخت‌نشده {owed:,} ریال")

    if feature_enabled("after_sales"):
        from aftersales.selectors import after_sales_requests_for

        cases = list(after_sales_requests_for(user).filter(customer=customer).order_by("-created_at")[:3])
        if cases:
            lines.append("\n# پرونده‌های پس از فروش")
            for case in cases:
                state = "بسته" if case.closed_at else "باز"
                lines.append(f"- {case.subject} ({state}، {case.status})")

    text = "\n".join(line for line in lines if line)
    return text[:MAX_CHARS]
