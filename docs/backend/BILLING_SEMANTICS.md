# Billing semantics

Every rule below is a **bounded default chosen by this codebase** where no
approved external contract fixed the rule. **This code claims no tax,
accounting, or legal compliance for any jurisdiction.** It applies whatever
percentage a deployment configures to one clearly defined base and does nothing
else. Where a rule would have required inventing a legal or accounting meaning,
the feature is absent rather than guessed.

Implementation: `billing/models.py`, `billing/money.py`, `billing/numbering.py`,
`billing/services.py`, `billing/payments.py`, `billing/ledger.py`.
Coverage: `billing/tests/test_rules.py`, `billing/tests/test_end_to_end.py`.

## Relationship to the existing sales records

`sales.Sale` (the operational record an agent files when a lead converts) and
`sales.SalesDocument` (the internal postal-tracking record) are **untouched**.
An `Invoice` may reference a `Sale`, but neither replaces the other and no
existing row was rewritten or migrated.

## Money

* `Decimal(18, 2)`, rounded **half-up at every step** rather than once at the
  end, so a stored total always equals the sum of the stored parts. Database
  check constraints enforce that equality, so a bug in the service cannot store
  a document whose header disagrees with its own lines.
* **One currency per deployment.** There is no currency column, because a second
  currency needs an exchange-rate policy nobody has approved.

## Document arithmetic

```text
line_total   = quantity × unit_price − line_discount
subtotal     = Σ line_total
taxable_base = subtotal − header_discount
tax          = round(taxable_base × tax_rate ÷ 100)
total        = taxable_base + tax
```

* A line discount is given **either** as a percentage **or** as an absolute
  amount, never both: two sources for one number is how a document ends up
  disagreeing with its own arithmetic. When a percentage is given it wins and
  the amount is derived from it.
* A line discount may not exceed its line; a header discount may not exceed the
  subtotal. Both are check constraints as well as service validation.
* `BILLING_MAX_DISCOUNT_PERCENT` (default `100.00`) bounds a line percentage.

## Tax is off by default

`BILLING_DEFAULT_TAX_RATE` defaults to `"0.00"`. The rate is snapshotted on the
document when it is created, so a later configuration change never rewrites an
issued document.

**Not implemented:** multiple tax rates per document, per-line tax, tax
exemptions, withholding, reverse charge, or any jurisdiction's filing format.
Each is a real legal decision and none is guessed.

## Numbering

A gap-free counter per document kind, formatted by `BILLING_NUMBER_FORMATS`
(defaults `QT-`, `SO-`, `INV-`, `PY-` with a six-digit sequence). The counter
row is locked with `select_for_update` before it is read, so two concurrent
issues take two different numbers.

Uniqueness has a second, independent guarantee: a unique constraint on each
document's `number`. Even a bug in the counter cannot produce two documents
sharing a number — it can only fail the write.

A configured format that omits `{sequence}` is refused where the operator can
still see why, rather than handing every document the same number.

The counter is a table row rather than a database sequence so that it is
restored with the rest of the data: after a restore, numbering continues from
the restored state instead of colliding with numbers already printed on a
customer's paperwork.

## A document is editable only while `draft`

Lines and header amounts may be changed only in `draft`. Once issued the
snapshot is immutable, so a printed document can never disagree with the stored
row. A mistake is corrected by cancelling and issuing a new document.

Line snapshots (`product_name_snapshot`, `product_sku_snapshot`, `unit_price`)
are captured when the line is written, so a later catalogue rename or reprice
never rewrites an existing document.

## Status graphs

Each document declares its own transition table and an unlisted jump is refused:

```text
Quotation  draft → sent → {accepted, rejected, expired, cancelled}
           accepted → {expired, cancelled}
Order      draft → confirmed → fulfilled ; draft|confirmed → cancelled
Invoice    draft → issued → cancelled
Cheque     registered → {deposited, returned, cancelled}
           deposited  → {cleared, bounced, returned}
           bounced    → {deposited, returned}
```

Conversion (quotation → order, order → invoice) **copies** into a new draft. The
source keeps its own number, status, and line snapshot, so what the customer
accepted stays readable exactly as accepted. A source yields at most one live
target.

## Issuing an invoice

One transaction does all three of:

1. snapshot each line's unit cost from the warehouse moving average, so profit
   is measured against what the sold units cost;
2. deduct the lines from the named warehouse — **off by default**
   (`BILLING_INVOICE_AFFECTS_STOCK`), see below;
3. post the debit to the customer ledger.

So an invoice can never exist without its ledger entry.

**The order owns the inventory lifecycle, not the invoice.** Client-1 raises the
invoice first and the order afterwards, and stock leaves when the *order* is
approved. If the invoice deducted as well, the same goods would leave twice for
one sale, so `BILLING_INVOICE_AFFECTS_STOCK` defaults to false. The capability
is kept for a deployment that invoices straight out of stock with no order step.

Note that step 1 still runs whenever the invoice names a warehouse, even with
the stock effect off: the cost snapshot is a *read*, and gross profit is
measured against it. Without that split, turning the deduction off would have
silently emptied the profit report.

## Order inventory lifecycle

| Event | Stock |
|---|---|
| order created (draft) | nothing moves |
| order approved | deducted, exactly once |
| approved order cancelled | returned, exactly once |
| approved order edited | only the difference moves |
| invoice issued | nothing (see above) |

"Exactly once" survives retries: `Order.stock_applied` records whether the
deduction has happened, and every movement carries an idempotency key derived
from the order and its `stock_revision` counter, so a repeated edit cannot reuse
the previous key and be silently swallowed.

A shortage never produces negative stock. If approval — or an edit to an
approved order — needs more than the warehouse holds, nothing moves, the order
is cancelled, and `موجودی کافی نبود` is appended to its note.

## Manual settlement of an invoice

Client-1 asked for a `پرداخت شده` box an operator can type into, where entering
exactly the outstanding amount marks the invoice settled.

This is a **display** decision and not an accounting one. It creates no Payment,
no PaymentAllocation and no ledger entry, and it never touches `paid_amount`,
the customer balance, receivables reporting or stock. `canonical_balance_due`
keeps reporting what the payment records alone say, and is published beside
`balance_due` so a reader can tell a manual settlement from a real one.

The transition is **one-way**. Once the typed figure has matched the outstanding
amount the invoice stays settled; editing the number afterwards changes what the
box shows and leaves the settlement alone. An invoice that has been declared
paid does not become unpaid because somebody retyped a field.

The whole override lives in three columns on `Invoice`
(`manual_paid_entry`, `manual_settled_at`, `manual_settled_by`) and can be
dropped without unwinding anything else, which is what a future receipt feature
will do.

## Invoice ↔ order linking

An invoice needs no order and is normally raised before one exists. One order
may gather several invoices. The link is a real nullable foreign key set through
`link_invoice_to_order`, after both documents exist — never a comparison of
document numbers as text, because a number is a display string.

An invoice with **no** warehouse has no stock effect and records no cost. It is
then reported as *unmeasured* in the profit report and excluded from the totals —
a missing cost is not a zero cost, and treating it as one would overstate profit.

Cancelling reverses both effects. An invoice with money already allocated to it
is refused: releasing an allocation is a separate, explicit decision.

## Payments

* **Registered once.** An `idempotency_key` makes a retried request return the
  original payment instead of taking the money twice.
* **A cheque is not cash.** `BILLING_CHEQUE_CREDITS_ON` defaults to `cleared`:
  the payment stays `pending` and credits the customer account only when the
  cheque clears. Returning or cancelling an uncleared cheque ends the payment
  with no ledger entry at all.
* **Allocation never exceeds either side** — not the payment's unallocated part,
  not the invoice's outstanding balance. A surplus stays on the customer account
  as a credit rather than inflating a settled document.
* **Nothing is deleted.** Releasing an allocation flags it reversed; cancelling
  a payment releases its allocations and appends the compensating ledger debit.

**Not implemented:** payment gateways, bank reconciliation, and automatic
matching. Each needs a provider contract that has not arrived.

## Installments

Equal amounts, with the rounding remainder placed on the **first** installment
rather than the last, so the plan sums exactly to the invoice total and the
customer never meets a surprise at the end. Bounded to 1–120 installments and
1–365 days apart (`BILLING_INSTALLMENT_INTERVAL_DAYS`, default 30).

An allocation fills installments from the earliest due date; releasing it unwinds
in reverse, leaving the plan exactly as it was.

**Not implemented:** interest, penalties, and late fees. All three are legal and
commercial decisions.

## The customer ledger

Append-only. Debit increases what the customer owes; credit reduces it. Every
entry carries the `balance_after` it produced, so a statement never replays
arithmetic and a corrupted middle row is detectable rather than silently
absorbed. A check constraint requires exactly one of debit or credit to be
non-zero, so no row can have an undefined effect on the balance.

`append_ledger_entry` locks the customer row before reading the running balance,
so two concurrent postings serialise instead of both computing from the same
stale total.

An **opening balance** (a balance carried in from before this system) is allowed
once per customer. A later correction belongs in the adjustment entries, where
it is visible as a correction.

The append-only property is enforced at the database role as well: the runtime
holds only `SELECT, INSERT` on `billing_customerledgerentry` and
`billing_chequestatushistory`.

## Reports

Receivables aging uses the conventional not-yet-due plus 1–30 / 31–60 / 61–90 /
90+ day buckets. **This grouping is presentational and carries no accounting or
legal meaning.** An invoice with no `due_at` is treated as due on issue, which is
what `BILLING_INVOICE_DUE_DAYS = 0` already means elsewhere.

The profit report is gross profit only: issued revenue minus the snapshotted
unit cost. It is not an income statement, applies no accounting basis (cash or
accrual), and allocates no overhead.

## Open decisions this file does not settle

* Whether an invoice may be raised directly from a `Sale` as a matter of policy
  (the code permits the reference; no workflow forces it).
* Credit notes as a document type distinct from cancellation.
* Any tax treatment beyond a single configurable percentage.
* Interest or penalty on overdue balances and installments.

Each stays absent until a product-owner decision arrives, rather than being
approximated.
