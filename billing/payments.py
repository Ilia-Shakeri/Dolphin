"""Payments, allocation to invoices, cheque lifecycle, and installment plans.

Money handling rules this module enforces, all recorded in
the "Billing semantics" section of `BACKEND_SPEC.md`:

* **A payment is registered once.** An `idempotency_key` makes a retried
  request return the original payment instead of taking the money twice.
* **A cheque is not cash.** By default a cheque payment stays `pending` and
  credits the customer account only when it clears
  (`BILLING_CHEQUE_CREDITS_ON`).
* **Allocation never exceeds either side.** A payment cannot allocate more than
  it holds, and an invoice cannot receive more than it owes; the surplus stays
  on the customer account as a credit.
* **Nothing is deleted.** Releasing an allocation flags it reversed and appends
  the compensating movement; cancelling a payment appends a ledger debit.
"""

import unicodedata
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Sum
from django.utils import timezone

from accounts.access import is_crm_identity
from accounts.models import User
from auditlog.services import log_activity
from billing.ledger import append_ledger_entry
from billing.money import clean_money, quantize_money
from billing.models import (
    FREE_TEXT_MAX_LENGTH,
    IDEMPOTENCY_KEY_MAX_LENGTH,
    REFERENCE_MAX_LENGTH,
    Cheque,
    ChequeStatusHistory,
    CustomerLedgerEntry,
    Installment,
    InstallmentPlan,
    Invoice,
    Payment,
    PaymentAllocation,
)
from billing.numbering import next_document_number
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from sales.models import Customer


ELEVATED_OPERATORS = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}
CHEQUE_FIELDS = {
    "bank_name", "bank_account", "branch_name", "serial_number",
    "account_holder", "due_date", "notes", "source",
    # The date written on the cheque. تاریخ روز is `created_at` and is
    # deliberately not accepted — the system stamps it. `is_registered` is
    # accepted and then ignored: it was a caller-supplied field until 1.3.6, and
    # dropping it from this set would turn an old call into an error rather than
    # into the harmless no-op it now is.
    "is_registered", "registered_on",
}


def cheque_credits_on_registration():
    """Whether a cheque credits the customer on arrival or only once cleared.

    The default became `registration` in 1.3.0 on the product owner's
    instruction: receiving a cheque is what settles the customer's account in
    their practice, and waiting for clearance left balances showing debts that
    both sides considered already paid.

    The consequence is that a bounce has to take the credit back, which is why
    `transition_cheque` reverses on BOUNCED. The setting is still read rather
    than hard-coded, so a deployment that accounts the other way can say so
    without a code change.
    """
    return str(getattr(settings, "BILLING_CHEQUE_CREDITS_ON", "registration")).lower() == "registration"


def customer_outstanding(customer):
    """What this customer still owes across every issued invoice.

    Cancelled and draft invoices are not debts, so they are not counted. The sum
    is computed from the invoices rather than from the ledger balance because
    the ledger also carries manual adjustments and opening balances, and بند ۳.۴
    is about invoices.
    """
    total = (
        Invoice.objects.filter(
            customer=customer, status=Invoice.Status.ISSUED
        ).aggregate(due=Sum(F("total_amount") - F("paid_amount")))["due"]
        or Decimal("0.00")
    )
    return quantize_money(max(total, Decimal("0.00")))


def _refuse_overpayment(*, customer, amount):
    """بند ۳.۴ — «اضافه پرداخت نداریم این آپشنو حذف کن».

    The product owner was asked what should happen to an overpayment — reject
    it, hold it as a credit, or refund it — and answered that overpayment does
    not occur in their business and the option should go. So it is rejected at
    the door: money that exceeds the debt cannot be recorded as a receipt
    against it.

    Only receipts that name a customer are checked. A receipt with no customer
    has no debt to measure against, and a disbursement is money going the other
    way.

    A refund is not this. The product owner's answer to بند ۵.۱ was that a
    refund is entered as a disbursement (پرداختی), which does not pass here.
    """
    if customer is None:
        return
    # Only meaningful once there is a debt to measure against.
    #
    # A receipt from a customer with no issued invoice is money on account, not
    # an overpayment: بند ۳.۱ says a receipt may sit unallocated and be assigned
    # to an invoice later, which is exactly that flow. Refusing it would have
    # blocked the ordinary case of taking a deposit before invoicing.
    if not Invoice.objects.filter(customer=customer, status=Invoice.Status.ISSUED).exists():
        return
    outstanding = customer_outstanding(customer)
    if amount > outstanding:
        raise BusinessRuleError({
            "amount": (
                "مبلغ رسید نمی‌تواند از بدهی مشتری "
                f"({outstanding}) بیشتر باشد. اضافه‌پرداخت ثبت نمی‌شود."
            )
        })


def _lock_payment_manager(actor):
    locked = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if locked is None or not is_crm_identity(locked):
        raise BusinessPermissionDenied("کاربر باید فعال باشد.")
    if locked.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("عملیات پرداخت مجاز نیست.")
    return locked


def _clean_line(value, *, field, limit, required=False):
    cleaned = " ".join(unicodedata.normalize("NFKC", str(value or "")).split())
    if required and not cleaned:
        raise BusinessRuleError({field: "این فیلد الزامی است."})
    if len(cleaned) > limit:
        raise BusinessRuleError({field: f"این فیلد نباید بیش از {limit} نویسه داشته باشد."})
    return cleaned


def _clean_text(value, *, field, limit):
    text = unicodedata.normalize("NFKC", str(value or ""))
    if len(text) > limit:
        raise BusinessRuleError({field: f"این فیلد نباید بیش از {limit} نویسه داشته باشد."})
    return text


@transaction.atomic
def register_payment(
    *,
    actor,
    # Defaults to nobody, because since 1.2.1 a disbursement may legitimately
    # name no customer and the model allows it. Without a default, a request
    # that simply omitted the key reached this function and raised TypeError —
    # a 500 where the rule it was breaking ("a receipt needs a customer") is
    # checked a few lines below and answers 400 like every other rule here.
    #
    # Passing `customer=None` explicitly always worked; only the missing key
    # crashed, which is exactly the shape a caller is most likely to send.
    customer=None,
    method,
    amount,
    direction=Payment.Direction.RECEIPT,
    payee="",
    received_at=None,
    reference="",
    bank_name="",
    bank_account="",
    idempotency_key="",
    notes="",
    cheque=None,
):
    actor = _lock_payment_manager(actor)
    if method not in Payment.Method.values:
        raise BusinessRuleError({"method": "روش پرداخت نامعتبر است."})
    if direction not in Payment.Direction.values:
        raise BusinessRuleError({"direction": "جهت پرداخت نامعتبر است."})
    payee = _clean_line(payee, field="payee", limit=255)
    is_receipt = direction == Payment.Direction.RECEIPT
    if is_receipt and customer is None:
        raise BusinessRuleError({"customer": "برای رسید، مشتری پرداخت‌کننده باید مشخص شود."})
    if not is_receipt and not payee:
        raise BusinessRuleError({"payee": "برای پرداخت خروجی باید گیرنده مشخص شود."})
    amount = clean_money(amount, field="amount", allow_zero=False)
    reference = _clean_line(reference, field="reference", limit=REFERENCE_MAX_LENGTH)
    bank_name = _clean_line(bank_name, field="bank_name", limit=120)
    bank_account = _clean_line(bank_account, field="bank_account", limit=64)
    if method != Payment.Method.BANK_TRANSFER and (bank_name or bank_account):
        # The database constraint says the same thing, but as an IntegrityError
        # naming a constraint. Refused here so the caller is told which field.
        raise BusinessRuleError({
            "bank_name": "اطلاعات بانکی فقط برای پرداخت با حواله بانکی است.",
            "bank_account": "اطلاعات بانکی فقط برای پرداخت با حواله بانکی است.",
        })
    idempotency_key = _clean_line(
        idempotency_key, field="idempotency_key", limit=IDEMPOTENCY_KEY_MAX_LENGTH
    )
    notes = _clean_text(notes, field="notes", limit=FREE_TEXT_MAX_LENGTH)
    received_at = received_at or timezone.now()

    if idempotency_key:
        # A retry is *this* payment asked for again, so the key is matched
        # together with the customer it names and checked against what it
        # claims. Three distinct outcomes, and only the first returns a row:
        #
        #   same key, same customer, same money  -> the original payment;
        #   same key, same customer, different   -> refused as a collision;
        #   same key, another customer           -> no match here at all, so it
        #     falls through to the unique constraint below and is refused
        #     without ever disclosing the other customer's payment.
        #
        # Matching on the key alone used to return whatever payment held it.
        # That both leaked a payment the caller had no scope for and silently
        # swallowed a second, genuine payment whose key happened to collide —
        # money taken, nothing recorded, and a 201 to say it went through.
        # Matched together with who it belongs to, never on the key alone —
        # that was the leak fixed earlier. A disbursement has no customer to
        # scope by, so it is scoped by its payee instead: the same retry, from
        # the same caller, about the same money.
        scope = (
            {"customer_id": customer.pk}
            if customer is not None
            else {"customer__isnull": True, "payee": payee}
        )
        existing = Payment.objects.filter(
            idempotency_key=idempotency_key, **scope
        ).first()
        if existing is not None:
            if existing.method != method or existing.amount != amount:
                raise BusinessConflictError({
                    "idempotency_key": "این کلید قبلاً برای پرداخت دیگری استفاده شده است."
                })
            return existing

    # A disbursement need not name a customer at all; when it does, the same
    # active check applies as for a receipt.
    locked_customer = None
    if customer is not None:
        locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
        if not locked_customer.is_active:
            raise BusinessConflictError({"customer": "مشتری غیرفعال است."})

    # بند ۳.۴ — overpayment is refused before anything is written.
    if direction == Payment.Direction.RECEIPT:
        _refuse_overpayment(customer=locked_customer, amount=amount)

    is_cheque = method == Payment.Method.CHEQUE
    if is_cheque and not isinstance(cheque, dict):
        raise BusinessRuleError({"cheque": "برای پرداخت با چک، اطلاعات چک الزامی است."})
    if not is_cheque and cheque:
        raise BusinessRuleError({"cheque": "اطلاعات چک فقط برای پرداخت با چک کاربرد دارد."})

    confirmed_now = (not is_cheque) or cheque_credits_on_registration()
    status = Payment.Status.CONFIRMED if confirmed_now else Payment.Status.PENDING

    try:
        payment = Payment.objects.create(
            number=next_document_number(Payment.NUMBER_KIND),
            customer=locked_customer,
            direction=direction,
            payee=payee,
            method=method,
            status=status,
            amount=amount,
            received_at=received_at,
            received_by=actor,
            reference=reference,
            bank_name=bank_name,
            bank_account=bank_account,
            idempotency_key=idempotency_key,
            notes=notes,
        )
    except IntegrityError as exc:
        raise BusinessConflictError({"idempotency_key": "این پرداخت قبلاً ثبت شده است."}) from exc

    if is_cheque:
        _create_cheque(actor=actor, payment=payment, amount=amount, data=cheque)

    if confirmed_now:
        _post_payment_credit(actor=actor, payment=payment)

    log_activity(
        actor=actor,
        operation="payment.registered",
        instance=payment,
        changes={
            # None on a disbursement that names no customer, which is a legal
            # state — the audit row records that rather than failing on it.
            "customer": locked_customer.pk if locked_customer is not None else None,
            "direction": direction,
            "payee": payee,
            "number": payment.number,
            "method": method,
            "amount": str(amount),
        },
    )
    return payment


def _post_payment_credit(*, actor, payment):
    """Post this payment to the customer ledger, in the direction it moved.

    A receipt credits: money arrived, so the customer owes less. A disbursement
    debits: money went the other way, so the mirror applies. Both follow the
    convention `CustomerLedgerEntry` states for itself — debit increases what
    the customer owes — rather than a second convention invented here.

    A disbursement with no customer posts nothing, and cannot: the ledger's
    customer is a required foreign key, and a payment to a supplier is not a
    customer event. That is a real limit of this ledger, not an omission.
    """
    if payment.customer_id is None:
        return
    if payment.direction == Payment.Direction.DISBURSEMENT:
        append_ledger_entry(
            actor=actor,
            customer=payment.customer,
            entry_type=CustomerLedgerEntry.EntryType.PAYMENT_MADE,
            debit=payment.amount,
            occurred_at=payment.received_at,
            reference_kind=CustomerLedgerEntry.ReferenceKind.PAYMENT,
            reference_id=payment.pk,
            reference_number=payment.number,
        )
        return
    append_ledger_entry(
        actor=actor,
        customer=payment.customer,
        entry_type=CustomerLedgerEntry.EntryType.PAYMENT_RECEIVED,
        credit=payment.amount,
        occurred_at=payment.received_at,
        reference_kind=CustomerLedgerEntry.ReferenceKind.PAYMENT,
        reference_id=payment.pk,
        reference_number=payment.number,
    )


def _create_cheque(*, actor, payment, amount, data):
    unknown = set(data) - CHEQUE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تنظیم نیست." for field in sorted(unknown)})
    due_date = data.get("due_date")
    if due_date is None:
        raise BusinessRuleError({"cheque": "برای چک باید تاریخ سررسید مشخص شود."})
    source = data.get("source", "") or ""
    if source and source not in Cheque.Source.values:
        raise BusinessRuleError({"cheque": "منبع چک نامعتبر است."})
    registered_on = data.get("registered_on") or None
    # Both axes are settled here and are not the caller's to choose.
    #
    # The product owner's rule is that a cheque recorded from a payment desk —
    # taken in or written out, it makes no difference — always starts «در
    # انتظار» and «ثبت نشده», and is moved by hand from the cheque page. Set
    # here rather than trusted from the request so a crafted call cannot file an
    # instrument into a state nobody chose, and so the two desks cannot drift
    # apart on it.
    is_registered = False
    try:
        return Cheque.objects.create(
            payment=payment,
            bank_name=_clean_line(data.get("bank_name"), field="cheque", limit=120, required=True),
            bank_account=_clean_line(data.get("bank_account", ""), field="cheque", limit=64),
            source=source,
            branch_name=_clean_line(data.get("branch_name", ""), field="cheque", limit=120),
            serial_number=_clean_line(data.get("serial_number"), field="cheque", limit=64, required=True),
            account_holder=_clean_line(data.get("account_holder", ""), field="cheque", limit=255),
            due_date=due_date,
            registered_on=registered_on,
            is_registered=is_registered,
            amount=amount,
            status=Cheque.Status.PENDING,
            notes=_clean_text(data.get("notes", ""), field="cheque", limit=FREE_TEXT_MAX_LENGTH),
        )
    except IntegrityError as exc:
        raise BusinessConflictError({
            "cheque": "چکی با این بانک و شماره سریال قبلاً ثبت شده است."
        }) from exc


@transaction.atomic
def spend_received_cheque(*, actor, cheque, payee, reason=""):
    """Endorse a received cheque to a third party.

    Deliberately creates nothing. The instrument handed over is the instrument
    already recorded, so this is a state change on that row and not a second
    cheque that would double the amount everywhere it is counted.

    It goes through `transition_cheque`, so the status graph, the append-only
    history, and the effect on the underlying payment all behave exactly as they
    do for every other cheque movement — including the part that matters most:
    a pending cheque payment is cancelled rather than left looking collectable,
    because this cheque is never going to clear into our account.
    """
    payee = _clean_line(payee, field="payee", limit=255, required=True)
    locked = Cheque.objects.select_for_update().get(pk=cheque.pk)
    if locked.payment.direction != Payment.Direction.RECEIPT:
        raise BusinessRuleError({
            "cheque": "فقط چکی که از مشتری دریافت شده قابل خرج کردن است."
        })
    updated = transition_cheque(
        actor=actor, cheque=locked, to_status=Cheque.Status.SPENT, reason=reason
    )
    updated.paid_to = payee
    # Handing a cheque to someone else is the moment it is on the books as a
    # real instrument, so حالت follows: a cheque that has been spent has been
    # registered by definition, and leaving it «ثبت نشده» meant the cheques page
    # showed a document that had left the building as one nobody had filed.
    #
    # Written directly rather than through `set_cheque_registration`, which locks
    # the same row this function already holds locked and writes its own history
    # for an axis the operator did not touch.
    updated.is_registered = True
    updated.save(update_fields=["paid_to", "is_registered", "updated_at"])
    return updated


@transaction.atomic
def set_cheque_registration(*, actor, cheque, is_registered, reason=""):
    """Move حالت — the axis that says whether the cheque has been registered.

    Separate from `transition_cheque` because the two axes are separate: a
    cheque can be registered while still pending, or spent while never having
    been registered. Folding this into the status graph would put them back into
    the single enum the product owner asked us to take apart.

    Deliberately has no effect on the payment underneath. Registering an
    instrument says where the paper is, not whether the money arrived — that is
    what وضعیت is for, and only it may cancel or credit anything.
    """
    actor = _lock_payment_manager(actor)
    locked = Cheque.objects.select_for_update().get(pk=cheque.pk)
    reason = _clean_text(reason, field="reason", limit=500)
    target = bool(is_registered)
    if locked.is_registered == target:
        return locked

    locked.is_registered = target
    locked.save(update_fields=["is_registered", "updated_at"])
    log_activity(
        actor=actor,
        operation="cheque.registration_changed",
        instance=locked,
        changes={
            "payment": locked.payment_id,
            "is_registered": target,
            "reason_provided": bool(reason),
        },
    )
    return locked


@transaction.atomic
def transition_cheque(*, actor, cheque, to_status, reason=""):
    """Move a cheque along its lifecycle, crediting the account when it clears.

    Atomic because it writes four things — the cheque's status, a history row,
    the payment underneath, and a ledger entry — and because it locks rows to do
    it. Without the decorator PostgreSQL refuses the first lock outright, and
    SQLite drops the lock and lets a half-finished transition survive a failure.
    """
    actor = _lock_payment_manager(actor)
    locked = Cheque.objects.select_for_update().select_related("payment").get(pk=cheque.pk)
    if to_status not in Cheque.Status.values:
        raise BusinessRuleError({"status": "وضعیت چک نامعتبر است."})
    allowed = Cheque.TRANSITIONS.get(locked.status, frozenset())
    if to_status not in allowed:
        raise BusinessConflictError({
            "status": f"چکی که در وضعیت «{locked.status}» است نمی‌تواند به «{to_status}» تغییر کند."
        })
    reason = _clean_text(reason, field="reason", limit=500)
    previous = locked.status
    locked.status = to_status
    locked.save(update_fields=["status", "updated_at"])
    ChequeStatusHistory.objects.create(
        cheque=locked,
        from_status=previous,
        to_status=to_status,
        changed_by=actor,
        reason=reason[:500],
    )

    payment = Payment.objects.select_for_update().get(pk=locked.payment_id)
    if to_status == Cheque.Status.PENDING and previous != Cheque.Status.BOUNCED:
        # Undoing an operation, which every state may now do. A bounce already
        # reversed the money on its way out, so returning from it costs nothing;
        # leaving CLEARED has to give back the credit that clearing posted, and
        # leaving SPENT has to undo the same reversal a spend performed.
        #
        # The payment goes back to PENDING either way, because that is what the
        # cheque now is: waiting again, and able to clear a second time. Without
        # this it would sit CANCELLED and a re-cleared cheque would credit
        # nobody — the correction would look applied and move no money.
        if payment.status == Payment.Status.CONFIRMED:
            cancel_payment(actor=actor, payment=payment, reason=reason)
            payment.refresh_from_db()
        payment.status = Payment.Status.PENDING
        payment.cancelled_at = None
        payment.save(update_fields=["status", "cancelled_at", "updated_at"])
    elif to_status == Cheque.Status.CLEARED and payment.status == Payment.Status.PENDING:
        payment.status = Payment.Status.CONFIRMED
        payment.save(update_fields=["status", "updated_at"])
        _post_payment_credit(actor=actor, payment=payment)
    elif to_status in {Cheque.Status.BOUNCED, Cheque.Status.SPENT}:
        # The money is not coming through this instrument. A pending payment
        # simply ends; a confirmed one is reversed through the normal path so
        # the ledger keeps both movements.
        #
        # BOUNCED belongs here since 1.3.0 and did not before. Now that a
        # cheque credits the customer on arrival, a bounce has to take that
        # credit back — and `cancel_payment` releases the payment's
        # allocations, which is precisely what "on bounce, add it back to the
        # invoice balance" asks for. Reversing rather than deleting keeps both
        # movements visible in the ledger, so the bounce is auditable instead
        # of looking like a cheque that never existed.
        if payment.status == Payment.Status.PENDING:
            payment.status = Payment.Status.CANCELLED
            payment.cancelled_at = timezone.now()
            payment.save(update_fields=["status", "cancelled_at", "updated_at"])
        elif payment.status == Payment.Status.CONFIRMED:
            cancel_payment(actor=actor, payment=payment, reason=reason)

    log_activity(
        actor=actor,
        operation="cheque.status_changed",
        instance=locked,
        changes={
            "payment": locked.payment_id,
            "status_from": previous,
            "status_to": to_status,
            "reason_provided": bool(reason),
        },
    )
    return locked


@transaction.atomic
def allocate_payment_across(*, actor, payment, splits):
    """Apply one receipt to several invoices at once. (بند ۳.۱ و ۳.۲)

    `splits` is a sequence of `{"invoice": Invoice, "amount": Decimal|None}`.
    This is the "place to specify how one receipt is divided between invoices"
    the product owner asked for.

    All of it or none of it. Splitting a receipt is one decision the operator
    makes on one screen, so a run that settled two invoices and then failed on
    the third would leave them looking at a state they never chose. The shared
    transaction means the failure reported is the only thing that happened.

    Each split goes through `allocate_payment`, so every rule that holds for a
    single allocation holds here too — same customer, issued invoice only,
    never more than the invoice's balance, never more than the receipt has
    left. Nothing is relaxed for being part of a batch.
    """
    actor = _lock_payment_manager(actor)
    if not splits:
        raise BusinessRuleError({"splits": "حداقل یک فاکتور را انتخاب کنید."})

    seen = set()
    for index, split in enumerate(splits):
        invoice = split.get("invoice")
        if invoice is None:
            raise BusinessRuleError({f"splits.{index}.invoice": "این فیلد الزامی است."})
        # The same invoice twice would hit the unique constraint underneath and
        # surface as a conflict about an allocation the operator never made.
        if invoice.pk in seen:
            raise BusinessRuleError({
                f"splits.{index}.invoice": "این فاکتور بیش از یک‌بار فهرست شده است."
            })
        seen.add(invoice.pk)

    allocations = []
    for split in splits:
        allocations.append(
            allocate_payment(
                actor=actor,
                payment=payment,
                invoice=split["invoice"],
                amount=split.get("amount"),
            )
        )
    return allocations


@transaction.atomic
def allocate_payment(*, actor, payment, invoice, amount=None):
    """Apply part or all of a confirmed payment to one issued invoice."""
    actor = _lock_payment_manager(actor)
    locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
    # Only money that came in can settle an invoice. A disbursement is money
    # going the other way; allowing it here would reduce a customer's balance
    # for a payment they never made.
    #
    # Enforced in the service rather than by a check constraint: a constraint on
    # PaymentAllocation cannot read the direction column, which lives on the
    # payment it points at. The test beside this is what keeps it honest.
    if locked_payment.direction != Payment.Direction.RECEIPT:
        raise BusinessRuleError({
            "payment": "فقط رسید را می‌توان به فاکتور تخصیص داد."
        })
    if locked_payment.status != Payment.Status.CONFIRMED:
        raise BusinessConflictError({"payment": "فقط پرداخت تأییدشده قابل تخصیص است."})
    locked_invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if locked_invoice.status != Invoice.Status.ISSUED:
        raise BusinessConflictError({"invoice": "فقط فاکتور صادرشده می‌تواند پرداخت دریافت کند."})
    if locked_invoice.customer_id != locked_payment.customer_id:
        raise BusinessRuleError({"invoice": "فاکتور و پرداخت باید متعلق به یک مشتری باشند."})

    available = locked_payment.unallocated_amount
    outstanding = locked_invoice.balance_due
    if available <= 0:
        raise BusinessConflictError({"payment": "این پرداخت به‌طور کامل تخصیص یافته است."})
    if outstanding <= 0:
        raise BusinessConflictError({"invoice": "این فاکتور قبلاً تسویه شده است."})

    amount = clean_money(amount, field="amount", allow_zero=False) if amount is not None else min(available, outstanding)
    if amount > available:
        raise BusinessRuleError({"amount": "مبلغ از بخش تخصیص‌نیافته این پرداخت بیشتر است."})
    if amount > outstanding:
        raise BusinessRuleError({"amount": "مبلغ از باقی‌مانده این فاکتور بیشتر است."})

    try:
        allocation = PaymentAllocation.objects.create(
            payment=locked_payment, invoice=locked_invoice, amount=amount, created_by=actor
        )
    except IntegrityError as exc:
        raise BusinessConflictError({
            "invoice": "این پرداخت قبلاً به این فاکتور تخصیص یافته است."
        }) from exc

    locked_payment.allocated_amount = quantize_money(locked_payment.allocated_amount + amount)
    locked_payment.save(update_fields=["allocated_amount", "updated_at"])
    locked_invoice.paid_amount = quantize_money(locked_invoice.paid_amount + amount)
    locked_invoice.save(update_fields=["paid_amount", "updated_at"])
    _apply_to_installments(invoice=locked_invoice, amount=amount)

    log_activity(
        actor=actor,
        operation="payment.allocated",
        instance=allocation,
        changes={
            "payment": locked_payment.pk,
            "invoice": locked_invoice.pk,
            "allocated_amount": str(amount),
        },
    )
    return allocation


@transaction.atomic
def release_allocation(*, actor, allocation, reason=""):
    """Undo one allocation without deleting it."""
    actor = _lock_payment_manager(actor)
    locked = PaymentAllocation.objects.select_for_update().get(pk=allocation.pk)
    if locked.is_reversed:
        raise BusinessConflictError({"is_reversed": "این تخصیص قبلاً آزاد شده است."})
    payment = Payment.objects.select_for_update().get(pk=locked.payment_id)
    invoice = Invoice.objects.select_for_update().get(pk=locked.invoice_id)

    locked.is_reversed = True
    locked.save(update_fields=["is_reversed", "updated_at"])
    payment.allocated_amount = quantize_money(payment.allocated_amount - locked.amount)
    payment.save(update_fields=["allocated_amount", "updated_at"])
    invoice.paid_amount = quantize_money(invoice.paid_amount - locked.amount)
    invoice.save(update_fields=["paid_amount", "updated_at"])
    _apply_to_installments(invoice=invoice, amount=-locked.amount)

    log_activity(
        actor=actor,
        operation="payment.allocation_released",
        instance=locked,
        changes={
            "payment": payment.pk,
            "invoice": invoice.pk,
            "allocated_amount": str(locked.amount),
            "reason_provided": bool(reason),
        },
    )
    return locked


#: What a correction may touch. `number` and `received_by` are not here and
#: never will be: the first is the document's identity and the second is who
#: recorded it, and a record you can rewrite the author of is not a record.
PAYMENT_EDITABLE_FIELDS = {
    "customer", "amount", "received_at", "reference", "bank_name", "payee",
    "notes", "status",
}

#: The cheque's own descriptive fields. Its two axes — وضعیت and حالت — are
#: deliberately absent: they move from the cheque page, through the services
#: that know what each move means for the money.
CHEQUE_EDITABLE_FIELDS = {
    "bank_name", "bank_account", "branch_name", "serial_number", "due_date",
    "registered_on",
}


@transaction.atomic
def update_payment(*, actor, payment, cheque=None, **data):
    """Correct a recorded payment, restating the ledger if the money changed.

    Only the platform admin. Checked here rather than only in the view, because
    a field being editable on screen is a convenience and never the
    authorisation.

    The hard part is not the fields, it is the ledger. A confirmed payment has
    already posted a credit; changing its amount or its customer makes that
    entry wrong. The ledger is append-only, so nothing is rewritten — the old
    entry is reversed and the new one posted, which is what a correction is in
    double entry and is exactly what `cancel_payment` and `_post_payment_credit`
    already do between them. No new accounting is invented here; the two
    existing primitives are simply called in order.

    The same applies to the status. Cancelling goes through `cancel_payment`, so
    allocations are released and the reversal is recorded; un-cancelling posts a
    fresh credit, which is the mirror of that and leaves both movements visible.
    """
    actor = _lock_payment_manager(actor)
    if actor.role != User.Role.PLATFORM_ADMIN:
        raise BusinessPermissionDenied("اصلاح پرداخت مجاز نیست.")

    unknown = set(data) - PAYMENT_EDITABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تنظیم نیست." for field in sorted(unknown)})

    locked = Payment.objects.select_for_update().get(pk=payment.pk)
    target_status = data.pop("status", locked.status)
    if target_status not in {Payment.Status.CONFIRMED, Payment.Status.CANCELLED}:
        raise BusinessRuleError({"status": "پرداخت فقط می‌تواند تأییدشده یا لغوشده باشد."})

    was_confirmed = locked.status == Payment.Status.CONFIRMED
    # What the ledger currently believes, captured before anything moves.
    old_amount = locked.amount
    old_customer_id = locked.customer_id

    if "amount" in data:
        data["amount"] = clean_money(data["amount"], field="amount", allow_zero=False)
    if "customer" in data:
        customer = data.pop("customer")
        if customer is None:
            if locked.direction == Payment.Direction.RECEIPT:
                raise BusinessRuleError({"customer": "رسید باید مشتری داشته باشد."})
            locked.customer = None
        else:
            locked.customer = Customer.objects.select_for_update().get(pk=customer.pk)
    for field in ("received_at", "reference", "bank_name", "payee", "notes"):
        if field in data:
            setattr(locked, field, data[field])
    released_for_amount = []
    if "amount" in data:
        # Allocation is not compulsory: money may simply sit against the
        # customer's account without being tied to any invoice. So a smaller
        # amount does not have to be refused — the surplus allocations are
        # released until what is left fits, and the payment keeps the rest.
        #
        # Newest first, because the earliest allocations are the ones the
        # operator most likely still means. Released through
        # `release_allocation`, so each invoice's paid amount and settlement
        # status are restored the same way they would be by hand, and the
        # release is recorded rather than silently undone.
        if data["amount"] < locked.allocated_amount:
            for allocation in (
                locked.allocations.filter(is_reversed=False).order_by("-id")
            ):
                if locked.allocated_amount <= data["amount"]:
                    break
                release_allocation(
                    actor=actor,
                    allocation=allocation,
                    reason="اصلاح مبلغ سند",
                )
                released_for_amount.append(allocation.pk)
                locked.refresh_from_db()
        locked.amount = data["amount"]

    locked.save()

    money_moved = locked.amount != old_amount or locked.customer_id != old_customer_id

    # --- the ledger, restated only when it has to be ------------------------
    if was_confirmed and target_status == Payment.Status.CANCELLED:
        cancel_payment(actor=actor, payment=locked, reason="اصلاح سند")
    elif was_confirmed and money_moved:
        # Reverse what was posted, then post what is true now. Two entries, both
        # kept, so the correction is auditable rather than silent.
        if old_customer_id is not None:
            append_ledger_entry(
                actor=actor,
                customer=Customer.objects.get(pk=old_customer_id),
                entry_type=CustomerLedgerEntry.EntryType.PAYMENT_CANCELLED,
                debit=old_amount,
                occurred_at=timezone.now(),
                reference_kind=CustomerLedgerEntry.ReferenceKind.PAYMENT,
                reference_id=locked.pk,
                reference_number=locked.number,
            )
        _post_payment_credit(actor=actor, payment=locked)
    elif locked.status == Payment.Status.CANCELLED and target_status == Payment.Status.CONFIRMED:
        # Cancelling is one-way, on the product owner's instruction: a document
        # that was cancelled is recorded again, not revived.
        #
        # 1.3.7 allowed the reverse and posted a fresh credit for it. That was
        # arithmetically sound and still the wrong thing to offer — an operator
        # who cancelled the wrong row could put it back with no trace of the
        # mistake except two ledger lines, while re-recording leaves a document
        # whose number says when it was really entered.
        raise BusinessRuleError({
            "status": "پرداخت لغوشده را نمی‌توان دوباره تأیید کرد. آن را از نو ثبت کنید."
        })

    # --- the cheque's own details -------------------------------------------
    if cheque:
        unknown = set(cheque) - CHEQUE_EDITABLE_FIELDS
        if unknown:
            raise BusinessRuleError({
                f"cheque.{field}": "این فیلد قابل تنظیم نیست." for field in sorted(unknown)
            })
        instrument = Cheque.objects.select_for_update().filter(payment=locked).first()
        if instrument is None:
            raise BusinessRuleError({"cheque": "این پرداخت چک ندارد."})
        for field, value in cheque.items():
            setattr(instrument, field, value)
        instrument.save()

    locked.refresh_from_db()
    log_activity(
        actor=actor,
        operation="payment.corrected",
        instance=locked,
        changes={
            "number": locked.number,
            "amount": str(locked.amount),
            "status": locked.status,
            "ledger_restated": bool(was_confirmed and money_moved),
            "allocations_released": released_for_amount,
        },
    )
    return locked


@transaction.atomic
def cancel_payment(*, actor, payment, reason=""):
    """Reverse a payment, releasing every allocation it still holds."""
    actor = _lock_payment_manager(actor)
    locked = Payment.objects.select_for_update().get(pk=payment.pk)
    if locked.status == Payment.Status.CANCELLED:
        raise BusinessConflictError({"status": "این پرداخت قبلاً لغو شده است."})
    was_confirmed = locked.status == Payment.Status.CONFIRMED

    for allocation in locked.allocations.filter(is_reversed=False):
        release_allocation(actor=actor, allocation=allocation, reason=reason)

    locked.refresh_from_db()
    locked.status = Payment.Status.CANCELLED
    locked.cancelled_at = timezone.now()
    locked.save(update_fields=["status", "cancelled_at", "updated_at"])

    if was_confirmed:
        append_ledger_entry(
            actor=actor,
            customer=locked.customer,
            entry_type=CustomerLedgerEntry.EntryType.PAYMENT_CANCELLED,
            debit=locked.amount,
            occurred_at=locked.cancelled_at,
            reference_kind=CustomerLedgerEntry.ReferenceKind.PAYMENT,
            reference_id=locked.pk,
            reference_number=locked.number,
        )
    log_activity(
        actor=actor,
        operation="payment.cancelled",
        instance=locked,
        changes={
            "number": locked.number,
            "amount": str(locked.amount),
            "reason_provided": bool(reason),
        },
    )
    return locked


def _apply_to_installments(*, invoice, amount):
    """Spread an allocation (or its release) across the plan, earliest due first.

    A negative `amount` unwinds in the reverse order, so releasing an allocation
    leaves the plan exactly as it was before that allocation was made.
    """
    plan = InstallmentPlan.objects.select_for_update().filter(
        invoice=invoice, status=InstallmentPlan.Status.ACTIVE
    ).first()
    if plan is None:
        return
    remaining = quantize_money(abs(amount))
    ordering = "sequence" if amount > 0 else "-sequence"
    installments = list(
        plan.installments.select_for_update()
        .exclude(status=Installment.Status.CANCELLED)
        .order_by(ordering)
    )
    for installment in installments:
        if remaining <= 0:
            break
        if amount > 0:
            room = installment.amount - installment.paid_amount
            applied = min(room, remaining)
        else:
            applied = -min(installment.paid_amount, remaining)
        if applied == 0:
            continue
        installment.paid_amount = quantize_money(installment.paid_amount + applied)
        installment.status = (
            Installment.Status.PAID
            if installment.paid_amount >= installment.amount
            else Installment.Status.PARTIALLY_PAID
            if installment.paid_amount > 0
            else Installment.Status.PENDING
        )
        installment.save(update_fields=["paid_amount", "status", "updated_at"])
        remaining = quantize_money(remaining - abs(applied))

    # Cancelled installments are excluded from the loop above and are therefore
    # excluded here too: counting them meant a plan with one cancelled line
    # could never reach `completed`, however fully the rest was paid.
    remaining = plan.installments.exclude(status=Installment.Status.CANCELLED)
    if remaining.exists() and all(item.status == Installment.Status.PAID for item in remaining):
        plan.status = InstallmentPlan.Status.COMPLETED
        plan.save(update_fields=["status", "updated_at"])
    elif plan.status == InstallmentPlan.Status.COMPLETED:
        plan.status = InstallmentPlan.Status.ACTIVE
        plan.save(update_fields=["status", "updated_at"])


@transaction.atomic
def create_installment_plan(
    *, actor, invoice, installment_count, start_date, interval_days=None, notes=""
):
    """Split an issued invoice into equal installments.

    Equal amounts, with the rounding remainder placed on the **first**
    installment rather than the last, so the plan always sums to the invoice
    total and the customer never meets a surprise at the end.
    """
    actor = _lock_payment_manager(actor)
    locked_invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if locked_invoice.status != Invoice.Status.ISSUED:
        raise BusinessConflictError({"invoice": "فقط فاکتور صادرشده قابل تقسیط است."})
    if InstallmentPlan.objects.filter(invoice=locked_invoice).exists():
        raise BusinessConflictError({"invoice": "این فاکتور قبلاً طرح اقساط دارد."})
    if isinstance(installment_count, bool) or not isinstance(installment_count, int):
        raise BusinessRuleError({"installment_count": "تعداد اقساط را به‌صورت عدد صحیح وارد کنید."})
    if installment_count < 1 or installment_count > 120:
        raise BusinessRuleError({"installment_count": "تعداد اقساط باید بین ۱ تا ۱۲۰ باشد."})
    if interval_days is None:
        interval_days = int(getattr(settings, "BILLING_INSTALLMENT_INTERVAL_DAYS", 30))
    if isinstance(interval_days, bool) or not isinstance(interval_days, int) or not (1 <= interval_days <= 365):
        raise BusinessRuleError({"interval_days": "بازه باید بین ۱ تا ۳۶۵ روز باشد."})
    if start_date is None:
        raise BusinessRuleError({"start_date": "برای طرح باید تاریخ سررسید نخست مشخص شود."})

    total = locked_invoice.total_amount
    if total <= 0:
        raise BusinessRuleError({"invoice": "فاکتور بدون مبلغ قابل تقسیط نیست."})
    base = quantize_money(total / installment_count)
    amounts = [base] * installment_count
    amounts[0] = quantize_money(total - base * (installment_count - 1))
    if any(value <= 0 for value in amounts):
        raise BusinessRuleError({
            "installment_count": "تعداد اقساط برای این مبلغ زیاد است؛ هر قسط باید بیشتر از صفر باشد."
        })

    plan = InstallmentPlan.objects.create(
        invoice=locked_invoice,
        total_amount=total,
        installment_count=installment_count,
        interval_days=interval_days,
        start_date=start_date,
        created_by=actor,
        notes=_clean_text(notes, field="notes", limit=FREE_TEXT_MAX_LENGTH),
    )
    Installment.objects.bulk_create([
        Installment(
            plan=plan,
            sequence=index + 1,
            due_date=start_date + timedelta(days=interval_days * index),
            amount=amounts[index],
        )
        for index in range(installment_count)
    ])
    # Money already applied to this invoice belongs to the plan from the start.
    if locked_invoice.paid_amount > 0:
        _apply_to_installments(invoice=locked_invoice, amount=locked_invoice.paid_amount)
    log_activity(
        actor=actor,
        operation="installment_plan.created",
        instance=plan,
        changes={
            "invoice": locked_invoice.pk,
            "installment_count": installment_count,
            "total_amount": str(total),
        },
    )
    return plan


@transaction.atomic
def cancel_installment_plan(*, actor, plan, reason=""):
    actor = _lock_payment_manager(actor)
    locked = InstallmentPlan.objects.select_for_update().get(pk=plan.pk)
    if locked.status == InstallmentPlan.Status.CANCELLED:
        raise BusinessConflictError({"status": "این طرح قبلاً لغو شده است."})
    locked.status = InstallmentPlan.Status.CANCELLED
    locked.save(update_fields=["status", "updated_at"])
    locked.installments.exclude(status=Installment.Status.PAID).update(
        status=Installment.Status.CANCELLED
    )
    log_activity(
        actor=actor,
        operation="installment_plan.cancelled",
        instance=locked,
        changes={"invoice": locked.invoice_id, "reason_provided": bool(reason)},
    )
    return locked


@transaction.atomic
def record_opening_balance(*, actor, customer, amount, occurred_at=None, notes=""):
    """Post a customer's balance carried in from before this system.

    Allowed once per customer: a second opening balance is a correction, and a
    correction belongs in the adjustment entries where it is visible as one.
    """
    actor = _lock_payment_manager(actor)
    amount = clean_money(amount, field="amount", allow_zero=False)
    locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
    if CustomerLedgerEntry.objects.filter(
        customer=locked_customer, entry_type=CustomerLedgerEntry.EntryType.OPENING_BALANCE
    ).exists():
        raise BusinessConflictError({"customer": "این مشتری قبلاً مانده ابتدای دوره دارد."})
    return append_ledger_entry(
        actor=actor,
        customer=locked_customer,
        entry_type=CustomerLedgerEntry.EntryType.OPENING_BALANCE,
        debit=amount,
        occurred_at=occurred_at or timezone.now(),
        notes=_clean_text(notes, field="notes", limit=FREE_TEXT_MAX_LENGTH),
    )
