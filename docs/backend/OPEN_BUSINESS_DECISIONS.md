# Open business decisions — elaboration (phase P1)

`KARIZ_PROJECT_HANDOFF.md` §14 is the authoritative register of which decisions
are open. This file is subordinate to it: it only expands the Tier-B families
into precise, answerable questions so the product owner can settle them without
a further round trip. If the two ever disagree, §14 wins.

**Nothing here proposes a business, tax, legal, or accounting answer.** Where
options are listed, they are an enumeration of the choices that exist, not a
recommendation. Choosing among them is a product-owner decision. Any question
left unanswered keeps its module blocked; no safe default is assumed.

Each family below gates a specific roadmap phase. Answering a family unblocks
exactly that phase and nothing else.

---

## A. Inventory and stock movement — gates P4

1. Is stock tracked at one location only, or across multiple warehouses?
2. If multiple: list them, and state whether an agent sees all or only their own.
3. What unit of measure applies — a single unit per product, or per-product units
   (piece / box / kilogram)? Are fractional quantities possible?
4. How is opening stock established: manual entry, import, or first purchase?
5. Which events change stock? Confirm each: sale, return, purchase/receipt,
   manual adjustment, transfer between warehouses, damage/write-off.
6. Does confirming a `Sale` (which exists today) decrement stock automatically,
   or is stock movement recorded separately?
7. **May stock go negative?** If yes, under what conditions and who may authorise
   it. If no, what should the system do when a sale would take it below zero.
8. Is stock ever reserved (held but not yet deducted)? If yes, by what event, and
   for how long before the reservation expires.
9. How is an incorrect movement fixed — a reversing entry, or an edit? (An edit
   conflicts with an append-only ledger; a reversal preserves history.)
10. Who may record each movement type: Sales Agent, Sales Manager, Platform Admin?

## B. Purchase cost and pricing — gates P4 and P8

1. Is purchase cost recorded per product, or per receipt/batch?
2. If cost changes over time, which cost applies to a sale — latest, weighted
   average, FIFO, or the cost captured on the sale itself?
3. Products currently carry one `current_price`. Are multiple price levels needed
   (retail / wholesale / customer-specific)? If yes, how is the applicable one
   chosen?
4. May an agent override the price on a sale? Within what limit, and who approves?
5. Are discounts per line, per document, or both?
6. Is a discount a percentage, a fixed amount, or either?
7. Who may see purchase cost and margin? (Cost visibility is usually narrower
   than price visibility — confirm explicitly per role.)

## C. Order and Quotation — gates P5

1. Is a Quotation needed at all for Client 1, or only an Order?
2. What is the lifecycle of each? List the exact statuses and which transitions
   are legal.
3. Does a Quotation expire? After how long, and what happens on expiry?
4. Who creates each, and who approves — is approval required before it is binding?
5. Does a Quotation convert into an Order, an Order into an Invoice, both, or
   neither? Conversion must not be assumed; state it explicitly.
6. On conversion, may quantities and prices be edited, or are they frozen?
7. Is the source always a Lead/Customer, or can an Order exist without one?
8. Numbering: what format, does it reset annually, and must it be gapless?
9. May an Order be cancelled after approval? Who may, and what happens to any
   linked stock or invoice?
10. How does this relate to the existing operational `Sale`? Does `Sale` remain,
    get replaced, or become a by-product of an Order?

## D. Accounting/legal Invoice — gates P6 (highest priority; PDF depends on it)

1. **What creates an Invoice?** Confirm which of these are permitted:
   directly from a Customer; from a `Sale`; from an Order; from a Quotation.
   More than one may be allowed.
2. Is the Invoice a formal tax document (فاکتور رسمی) or an internal commercial
   document? This changes the legal requirements substantially.
3. Which tax applies — VAT/ارزش افزوده at a stated rate, none, or per-product
   rates? State the exact current rate(s) and any exempt categories.
4. Is the entered price tax-inclusive or tax-exclusive?
5. Order of operations: is tax computed before or after discount? State the exact
   sequence, because the two give different totals.
6. Rounding: to what unit (ریال / تومان / 1000), at which step (per line or on the
   total), and using which rule (half-up, half-even, truncate)?
7. Numbering: format, annual reset, and whether gapless sequence is legally
   required. If gapless, cancellation cannot delete a number.
8. Correction: is an issued invoice edited, superseded by a corrected invoice, or
   reversed by a credit note? Physical deletion will not be implemented.
9. Cancellation: who may cancel, until when, and what happens to linked payments?
10. Which fields must be frozen (snapshotted) on issue so that later product or
    customer edits cannot alter a historical invoice?
11. **Please supply one redacted real invoice** (customer identifiers removed).
    This single item resolves many of the questions above and is the main
    blocker for both P6 and P9.

## E. Payment, cheque, and installment — gates P7

1. Which payment methods exist: cash, card/POS, bank transfer, cheque,
   installment, other?
2. **Must a payment always be allocated to an Invoice**, or may it sit on the
   customer's account and be allocated later? Both are common; the choice is
   architectural and cannot be inferred.
3. May one payment cover several invoices, and one invoice receive several
   payments?
4. Partial payment: allowed? Does it change the invoice status?
5. Overpayment: refused, held as credit, or refunded?
6. Cheque — list the exact states and legal transitions (for example received,
   deposited, cleared, bounced, returned, replaced). Which dates are recorded:
   write date, due date, clearing date?
7. What happens when a cheque bounces — to the invoice, to the customer balance,
   and to any dependent record?
8. Installments: who defines the schedule, is interest or a late fee applied, and
   how is it calculated?
9. What marks an installment late, and does anything happen automatically?
10. May a payment be reversed or refunded, by whom, and does that require a
    separate document?
11. Who may record a payment versus confirm/approve it?

## F. Customer account and ledger — gates P7

1. Sign convention: does a positive balance mean the customer owes us, or we owe
   them? State it explicitly — this cannot be guessed safely.
2. Which events post to the ledger: invoice issued, payment received, cheque
   cleared, cheque bounced, credit note, manual adjustment, opening balance?
3. Is there an opening balance per customer, and how is it entered?
4. May a manual adjustment be posted? By whom, and does it require a reason and
   approval?
5. Is the ledger strictly append-only (corrections posted as new reversing
   entries)? This is strongly recommended technically, but confirm it is
   acceptable operationally.
6. Is the balance stored, or always derived by summing entries?
7. Who may view another customer's balance — does a Sales Agent see the balance
   of customers assigned to them?

## G. Receivables and profit/loss — gates P8

1. Accounting basis: cash or accrual? This determines when revenue is recognised
   and changes every number in both reports.
2. Receivables: is an amount outstanding from invoice issue, or from due date?
3. What ageing buckets are wanted (for example 0–30 / 31–60 / 61–90 / 90+ days)?
4. Are cheques not yet cleared counted as received, or as receivable?
5. Profit definition: revenue minus cost of goods sold only, or minus other costs
   too? If other costs, where do they come from — there is no expense module.
6. Which cost figure feeds profit — see question B.2.
7. Are returns, cancellations, and discounts deducted from revenue?
8. Reporting period: calendar month, Jalali month, or arbitrary range? Is there a
   period-close after which figures are frozen?
9. Who may view profit figures?

## H. PDF and printing — gates P9 (expected in the first operational delivery)

1. Which documents need to print: Invoice, Order, Quotation, receipt, delivery
   note, others?
2. **Please supply a redacted example of each** — layout is otherwise guesswork.
3. Paper size and orientation (A4/A5, portrait/landscape).
4. Which logo and company details appear in the header?
5. Is any fixed legal text, stamp, or signature block required?
6. ~~Is a Jalali date shown, a Gregorian date, or both?~~ **RESOLVED 2026-08-16 (`BIZ-007`):** Jalali everywhere a user reads or types; canonical Gregorian ISO in storage and the API. Contract: `docs/backend/DATE_AND_CALENDAR.md`.
7. Are amounts also written in words? In Persian?
8. Must the printed document carry a unique identifier or barcode/QR?
9. Who may download or print each document type?

## I. Files and documents — gates P10

1. Which record types need attachments: Customer, Lead, Sale, Invoice,
   After-Sales request?
2. Which file types are permitted, and what is the maximum size per file?
3. Is there a total storage budget per deployment?
4. How long are files retained, and may they be deleted? By whom?
5. Who may download a file — the same scope as the parent record, or narrower?
6. Is virus/malware scanning required before a file becomes downloadable?
7. Must files be included in backups? Their size affects RPO/RTO materially.

## J. External integrations — gates P11, each independently

For **each** provider (website/store, payment gateway, accounting software, SMS,
email, telephony), all of the following are required before any adapter work
starts. A provider missing any item stays `BLOCKED_EXTERNAL`.

1. Exact provider name and product.
2. Official API documentation (URL or file).
3. Sandbox/test credentials, delivered through an approved secret channel —
   never in chat, a ticket, or this repository.
4. Direction of data flow, and which system is authoritative on conflict.
5. Which records synchronise, and at what frequency.
6. Idempotency: how a duplicate delivery is detected and ignored.
7. Retry and failure policy, including who is alerted.
8. Reconciliation procedure when the two systems disagree.
9. A named technical contact at the provider.
10. Who owns the commercial relationship and the credentials.

---

## How to answer

Answer inline in this file, or in any convenient form. Partial answers are
useful: a fully answered family unblocks its phase immediately, even if other
families remain open. Families are independent except where the answers
themselves create a dependency (for example, if D.1 makes an Invoice originate
only from an Order, then P5 must precede P6).
