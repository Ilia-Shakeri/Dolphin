# Inventory semantics

Every rule below is a **bounded default chosen by this codebase**, not a rule
imported from an approved external contract. None of them encodes an accounting
standard or a legal requirement. Each is per-deployment configurable or
changeable without touching business logic elsewhere, and each is stated here so
that a later product-owner decision can overrule it deliberately rather than by
accident.

Implementation: `inventory/models.py`, `inventory/services.py`.
Coverage: `inventory/tests/test_stock.py`.

## Quantities are whole units

`sales.Sale.quantity` and every document line are positive integers, so a
fractional unit could never travel the existing sales path. Stock therefore
counts in whole units too.

**What would change it:** a customer who sells by weight or length. That is a
column change plus a rounding policy for partial issues, not a re-interpretation
of these rules.

## Cost is a moving weighted average

Each incoming movement recomputes the average over the whole on-hand quantity:

```text
new_average = (old_quantity × old_average + received_quantity × received_cost)
              ÷ (old_quantity + received_quantity)
```

rounded half-up to two decimals. When the level is zero or below, the arriving
cost simply becomes the average. Outgoing movements consume the average in force
and never change it.

A return with no stated cost re-enters at the average in force, because that is
what the stock cost when it left. Nothing is invented.

**Not implemented:** FIFO, LIFO, standard costing, and landed-cost allocation.
Choosing one of those is a real accounting decision with tax consequences, so
none is guessed here.

## Negative stock is refused

`INVENTORY_ALLOW_NEGATIVE_STOCK` defaults to false. An issue that would drive a
warehouse below zero is refused and leaves no movement behind.

**Why this default:** a warehouse that silently goes negative hides a counting
error rather than surfacing it, and no approved contract asked for the
permissive behaviour. A deployment that genuinely sells before receipting turns
it on explicitly.

## The movement ledger is append-only

A movement is never edited and never deleted. A mistake is corrected by a
compensating movement, so the ledger always reconstructs the current level and
every historical level stays reproducible.

`StockItem` (quantity and average cost) is **derived state**: every field is
reproducible from the movements. It exists so a stock read is one indexed row
rather than an aggregate over the whole ledger, and it is written only inside
the movement service under `select_for_update`.

The append-only property is enforced twice: the service never issues an update
or delete, and the PostgreSQL runtime role holds only `SELECT, INSERT` on
`inventory_stockmovement` (`scripts/bootstrap-postgres.sh`, proven by
`scripts/verify-postgres-privileges.sql`).

## Concurrency

`record_stock_movement` takes the row lock on the affected `StockItem` **before**
reading it. Two concurrent issues of the same product therefore serialise, and
the second sees the first one's level rather than both reading the pre-change
value and jointly overselling.

## Warehouses

* At most one warehouse is the default, and only an active one may hold the
  flag — enforced by a partial unique constraint plus a check constraint, not
  only by service code.
* A warehouse still holding stock cannot be deactivated. Deactivating it would
  strand that stock: it would stay in the ledger but leave every level report.
  Transfer it out first.
* A transfer is two movements in one transaction. The outgoing leg runs first,
  so an insufficient level fails before anything is created. The stock keeps the
  cost it carried at the source, so a transfer never changes total inventory
  value.

## Link to billing

`StockMovement` records a billing document as a **soft reference**
(`reference_kind` + `reference_id`), not a foreign key. Inventory must stay
usable in a deployment whose manifest does not enable billing at all, and a hard
foreign key would make the two features inseparable.

Issuing an invoice that names a warehouse deducts its lines and snapshots the
unit cost onto the invoice line; cancelling that invoice returns the stock at
the snapshotted cost. Both use an idempotency key derived from the invoice and
line id, so a retry cannot apply the movement twice.
