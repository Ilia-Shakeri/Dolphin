"""How a score is worked out — one strategy per person type (decision D21).

Each strategy lists its factors with a default weight, and measures each
factor as a ratio between 0 and 1 with a Persian sentence saying why. A
factor that cannot be measured for this person (no due dates yet, a module
this deployment does not run) is *not applicable*: it is left out and the
score is taken over the factors that are, so a new customer is not punished
for history they cannot have had.

The strategies read **every** row about a person, not a viewer's slice of
them: a score is a property of the person. Who may *see* a score is decided
where it is shown (`profiles.cards`), never here.

Everything is computed for a batch of people at once (`prepare`), so the
nightly recalculation is a handful of grouped queries rather than a handful
per person. A single profile is simply a batch of one.

Another strategy (an AI model, a deployment's own rules) is one more class
with the same interface, registered in `STRATEGIES`.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from statistics import median

from django.db.models import Count, Max, Min, Q, Sum

from common.deployment.profile import feature_enabled
from common.formatting import persian_digits


@dataclass(frozen=True)
class Factor:
    key: str
    label: str
    default_weight: int


@dataclass(frozen=True)
class FactorResult:
    key: str
    #: 0..1, or `None` when the factor cannot be measured for this person.
    ratio: object
    reason: str


def _n(value):
    return persian_digits(value)


def _ladder(value, steps):
    """The ratio of the first `(bound, ratio)` step `value` is at or under.
    Every ladder here ends in an `inf` step, so one always matches."""
    for bound, ratio in steps:
        if value <= bound:
            return ratio
    return 0.0


def _rank(value, population):
    """Where `value` sits among `population` (which includes it): 0 = the
    lowest, 1 = the highest. Alone in the population is the highest."""
    if len(population) <= 1:
        return 1.0
    below = sum(1 for item in population if item < value)
    return below / (len(population) - 1)


class ScoringStrategy:
    key = ""
    person_type = ""
    factors = ()

    def prepare(self, people, *, now):
        raise NotImplementedError

    def evaluate(self, person, context, *, now):
        raise NotImplementedError


# --- Customers -----------------------------------------------------------------

CUSTOMER_FACTORS = (
    Factor("recency", "تازگی آخرین تعامل", 25),
    Factor("frequency", "دفعات خرید", 20),
    Factor("monetary", "ارزش خرید", 20),
    Factor("punctuality", "خوش‌حسابی", 25),
    Factor("engagement", "ارتباط اخیر", 10),
)


class CustomerRuleStrategy(ScoringStrategy):
    key = "customer_rules_v1"
    person_type = "customer"
    factors = CUSTOMER_FACTORS

    #: Windows each factor looks back over.
    PURCHASE_WINDOW = timedelta(days=365)
    ENGAGEMENT_WINDOW = timedelta(days=90)

    def prepare(self, people, *, now):
        from billing.models import Installment, Invoice, Payment
        from communications.models import InboundSMS
        from sales.models import Interaction, Sale

        ids = [person.pk for person in people]
        purchase_since = now - self.PURCHASE_WINDOW
        engagement_since = now - self.ENGAGEMENT_WINDOW
        use_invoices = feature_enabled("invoices")

        last = {pk: [] for pk in ids}

        def note_latest(rows, key):
            for row in rows:
                if row["latest"] is not None:
                    last.setdefault(row[key], []).append(row["latest"])

        if feature_enabled("leads"):
            note_latest(
                Interaction.objects.filter(customer_id__in=ids).values("customer_id").annotate(latest=Max("occurred_at")),
                "customer_id",
            )
            note_latest(
                Interaction.objects.filter(customer__isnull=True, lead__customer_id__in=ids)
                .values("lead__customer_id").annotate(latest=Max("occurred_at")),
                "lead__customer_id",
            )
        if feature_enabled("sales"):
            note_latest(
                Sale.objects.filter(customer_id__in=ids, status=Sale.Status.CONFIRMED)
                .values("customer_id").annotate(latest=Max("sold_at")),
                "customer_id",
            )
        if use_invoices:
            note_latest(
                Invoice.objects.filter(customer_id__in=ids, status=Invoice.Status.ISSUED)
                .values("customer_id").annotate(latest=Max("issued_at")),
                "customer_id",
            )
        if feature_enabled("payments"):
            note_latest(
                Payment.objects.filter(customer_id__in=ids, direction=Payment.Direction.RECEIPT)
                .values("customer_id").annotate(latest=Max("received_at")),
                "customer_id",
            )

        # Purchases: issued invoices when this deployment invoices, confirmed
        # sales otherwise — never both, or an invoiced sale counts twice (D4).
        if use_invoices:
            purchases = Invoice.objects.filter(status=Invoice.Status.ISSUED, issued_at__gte=purchase_since)
            amount_field, purchase_word = "total_amount", "فاکتور صادرشده"
        elif feature_enabled("sales"):
            purchases = Sale.objects.filter(status=Sale.Status.CONFIRMED, sold_at__gte=purchase_since)
            amount_field, purchase_word = "total_amount", "فروش تأییدشده"
        else:
            purchases, amount_field, purchase_word = None, "", ""
        purchase_count, purchase_total, population = {}, {}, []
        if purchases is not None:
            for row in purchases.values("customer_id").annotate(n=Count("id"), total=Sum(amount_field)):
                population.append(row["total"] or Decimal("0"))
                if row["customer_id"] in last:
                    purchase_count[row["customer_id"]] = row["n"]
                    purchase_total[row["customer_id"]] = row["total"] or Decimal("0")

        # Punctuality: of what fell due in the window, how much is still
        # outstanding past its due date. There is no "paid on" date to
        # judge lateness after the fact, so this measures what is overdue now.
        due = {pk: 0 for pk in ids}
        overdue = {pk: 0 for pk in ids}
        if use_invoices:
            invoices = Invoice.objects.filter(customer_id__in=ids, status=Invoice.Status.ISSUED).filter(
                Q(due_at__gte=purchase_since, due_at__lte=now)
                | Q(due_at__isnull=True, issued_at__gte=purchase_since, issued_at__lte=now)
            )
            for invoice in invoices:
                due[invoice.customer_id] += 1
                if invoice.balance_due > 0:
                    overdue[invoice.customer_id] += 1
        if feature_enabled("payments"):
            today = now.date()
            instalments = Installment.objects.filter(
                plan__invoice__customer_id__in=ids,
                due_date__gte=(now - self.PURCHASE_WINDOW).date(),
                due_date__lt=today,
            ).values("plan__invoice__customer_id", "status")
            for row in instalments:
                customer_id = row["plan__invoice__customer_id"]
                due[customer_id] += 1
                if row["status"] in ("pending", "partially_paid"):
                    overdue[customer_id] += 1

        contacts = {pk: 0 for pk in ids}
        if feature_enabled("leads"):
            for row in (
                Interaction.objects.filter(occurred_at__gte=engagement_since)
                .filter(Q(customer_id__in=ids) | Q(customer__isnull=True, lead__customer_id__in=ids))
                .values("customer_id", "lead__customer_id")
            ):
                customer_id = row["customer_id"] or row["lead__customer_id"]
                if customer_id in contacts:
                    contacts[customer_id] += 1
        if feature_enabled("inbound_sms"):
            for row in (
                InboundSMS.objects.filter(customer_id__in=ids, provider_received_at__gte=engagement_since)
                .values("customer_id").annotate(n=Count("id"))
            ):
                contacts[row["customer_id"]] += row["n"]

        return {
            "last": {pk: max(values) if values else None for pk, values in last.items()},
            "purchase_count": purchase_count,
            "purchase_total": purchase_total,
            "population": population,
            "purchase_word": purchase_word,
            "measures_purchases": purchases is not None,
            "due": due,
            "overdue": overdue,
            "contacts": contacts,
        }

    def evaluate(self, person, context, *, now):
        pk = person.pk
        results = []

        latest = context["last"].get(pk)
        if latest is None:
            results.append(FactorResult("recency", 0.0, "هیچ تماس، خرید یا پرداختی ثبت نشده است."))
        else:
            days = max(0, (now - latest).days)
            ratio = _ladder(days, [(7, 1.0), (30, 0.75), (90, 0.45), (180, 0.2), (float("inf"), 0.0)])
            results.append(FactorResult("recency", ratio, f"آخرین تعامل {_n(days)} روز پیش بوده است."))

        if not context["measures_purchases"]:
            results.append(FactorResult("frequency", None, "خرید در این استقرار ثبت نمی‌شود."))
            results.append(FactorResult("monetary", None, "خرید در این استقرار ثبت نمی‌شود."))
        else:
            count = context["purchase_count"].get(pk, 0)
            ratio = _ladder(count, [(0, 0.0), (1, 0.3), (2, 0.5), (5, 0.75), (float("inf"), 1.0)])
            results.append(FactorResult(
                "frequency", ratio, f"{_n(count)} {context['purchase_word']} در ۱۲ ماه گذشته."
            ))
            total = context["purchase_total"].get(pk)
            if not total:
                results.append(FactorResult("monetary", 0.0, "در ۱۲ ماه گذشته خریدی نداشته است."))
            else:
                rank = _rank(total, context["population"])
                if len(context["population"]) <= 1:
                    reason = "تنها مشتریِ خریدار در ۱۲ ماه گذشته است."
                elif rank == 0:
                    reason = "کمترین مجموع خرید را در میان مشتریانِ خریدار دارد."
                else:
                    reason = f"مجموع خریدش از {_n(round(rank * 100))}٪ مشتریانِ خریدار بیشتر است."
                results.append(FactorResult("monetary", rank, reason))

        due, overdue = context["due"].get(pk, 0), context["overdue"].get(pk, 0)
        if not due:
            results.append(FactorResult("punctuality", None, "در ۱۲ ماه گذشته سررسیدی نداشته است."))
        else:
            ratio = 1 - overdue / due
            reason = (
                f"هیچ‌کدام از {_n(due)} سررسید گذشته معوق نیست."
                if not overdue
                else f"{_n(overdue)} از {_n(due)} سررسید گذشته هنوز پرداخت نشده است."
            )
            results.append(FactorResult("punctuality", ratio, reason))

        contacts = context["contacts"].get(pk, 0)
        ratio = _ladder(contacts, [(0, 0.0), (2, 0.4), (4, 0.7), (float("inf"), 1.0)])
        results.append(FactorResult("engagement", ratio, f"{_n(contacts)} تماس یا پیام در ۹۰ روز گذشته."))
        return results


# --- Users ---------------------------------------------------------------------

USER_FACTORS = (
    Factor("task_on_time", "انجام به‌موقع وظیفه‌ها", 20),
    Factor("conversion", "نرخ تبدیل سرنخ", 30),
    Factor("follow_up_speed", "سرعت پیگیری", 20),
    Factor("activity", "فعالیت", 20),
    Factor("missed_call_follow_up", "پیگیری تماس‌های بی‌پاسخ", 10),
)


class UserRuleStrategy(ScoringStrategy):
    key = "user_rules_v1"
    person_type = "user"
    factors = USER_FACTORS

    WINDOW = timedelta(days=90)
    ACTIVITY_WINDOW = timedelta(days=30)

    def prepare(self, people, *, now):
        from sales.models import Interaction, Lead
        from tasks.models import Task

        ids = [person.pk for person in people]
        since = now - self.WINDOW
        context = {"tasks": {}, "conversion": {}, "speed": {}, "activity": {}, "activity_population": []}

        if feature_enabled("tasks"):
            for row in (
                Task.objects.filter(assignee_id__in=ids, due_at__gte=since, due_at__lte=now)
                .exclude(status=Task.Status.CANCELLED)
                .values("assignee_id", "status", "due_at", "completed_at")
            ):
                bucket = context["tasks"].setdefault(row["assignee_id"], [0, 0])
                bucket[0] += 1
                if row["status"] == Task.Status.DONE and row["completed_at"] and row["completed_at"] <= row["due_at"]:
                    bucket[1] += 1

        if feature_enabled("leads"):
            for row in (
                Lead.objects.filter(
                    assigned_to_id__in=ids,
                    status__in=[Lead.Status.COMPLETED, Lead.Status.CANCELLED],
                    closed_at__gte=since,
                )
                .values("assigned_to_id")
                .annotate(decided=Count("id"), completed=Count("id", filter=Q(status=Lead.Status.COMPLETED)))
            ):
                context["conversion"][row["assigned_to_id"]] = (row["completed"], row["decided"])

            leads = list(
                Lead.objects.filter(assigned_to_id__in=ids, assigned_at__gte=since).values("id", "assigned_to_id", "assigned_at")
            )
            first_call = {
                (row["lead_id"], row["agent_id"]): row["first"]
                for row in Interaction.objects.filter(lead_id__in=[lead["id"] for lead in leads])
                .values("lead_id", "agent_id").annotate(first=Min("occurred_at"))
            }
            for lead in leads:
                answered = first_call.get((lead["id"], lead["assigned_to_id"]))
                if answered is not None and answered >= lead["assigned_at"]:
                    hours = (answered - lead["assigned_at"]).total_seconds() / 3600
                elif now - lead["assigned_at"] > timedelta(hours=72):
                    hours = float("inf")  # still waiting, and already late
                else:
                    continue  # still inside its window; no verdict yet
                context["speed"].setdefault(lead["assigned_to_id"], []).append(hours)

            activity_since = now - self.ACTIVITY_WINDOW
            counts = {
                row["agent_id"]: row["n"]
                for row in Interaction.objects.filter(occurred_at__gte=activity_since)
                .values("agent_id").annotate(n=Count("id"))
            }
            context["activity"] = counts
            context["activity_population"] = list(counts.values())
        return context

    def evaluate(self, person, context, *, now):
        pk = person.pk
        results = []

        if not feature_enabled("tasks"):
            results.append(FactorResult("task_on_time", None, "وظیفه‌ها در این استقرار فعال نیست."))
        else:
            due, on_time = context["tasks"].get(pk, (0, 0))
            if not due:
                results.append(FactorResult("task_on_time", None, "در ۹۰ روز گذشته وظیفهٔ سررسیدشده‌ای نداشته است."))
            else:
                results.append(FactorResult(
                    "task_on_time", on_time / due, f"{_n(on_time)} از {_n(due)} وظیفه به‌موقع انجام شده است."
                ))

        completed, decided = context["conversion"].get(pk, (0, 0))
        if not decided:
            results.append(FactorResult("conversion", None, "در ۹۰ روز گذشته سرنخی به نتیجه نرسیده است."))
        else:
            rate = completed / decided
            results.append(FactorResult(
                "conversion", rate,
                f"{_n(completed)} از {_n(decided)} سرنخ تصمیم‌گرفته‌شده تکمیل شده ({_n(round(rate * 100))}٪).",
            ))

        waits = context["speed"].get(pk, [])
        if not waits:
            results.append(FactorResult("follow_up_speed", None, "در ۹۰ روز گذشته سرنخی به او واگذار نشده است."))
        else:
            middle = median(waits)
            ratio = _ladder(middle, [(4, 1.0), (24, 0.75), (72, 0.4), (float("inf"), 0.15)])
            if middle == float("inf"):
                reason = "بیشتر سرنخ‌های واگذارشده پس از سه روز هنوز تماسی نگرفته‌اند."
            else:
                reason = f"میانهٔ فاصلهٔ واگذاری تا اولین تماس {_n(round(middle))} ساعت است."
            results.append(FactorResult("follow_up_speed", ratio, reason))

        population = context["activity_population"]
        mine = context["activity"].get(pk, 0)
        if not population:
            results.append(FactorResult("activity", None, "در ۳۰ روز گذشته هیچ تماسی در سامانه ثبت نشده است."))
        elif not mine:
            results.append(FactorResult("activity", 0.0, "در ۳۰ روز گذشته تماسی ثبت نکرده است."))
        else:
            rank = _rank(mine, population)
            results.append(FactorResult(
                "activity", rank, f"{_n(mine)} تماس در ۳۰ روز گذشته — بیشتر از {_n(round(rank * 100))}٪ همکاران فعال."
            ))

        results.append(FactorResult(
            "missed_call_follow_up", None, "با اتصال سامانهٔ تلفنی (VoIP) سنجیده می‌شود."
        ))
        return results


STRATEGIES = {
    "customer": CustomerRuleStrategy(),
    "user": UserRuleStrategy(),
}
