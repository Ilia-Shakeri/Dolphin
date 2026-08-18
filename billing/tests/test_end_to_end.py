from datetime import date
from decimal import Decimal
from django.test import TestCase
from accounts.models import User
from sales.services import create_customer_with_phone, create_product, create_product_category
from inventory.services import create_warehouse, record_stock_movement
from inventory.models import StockItem, StockMovement
from billing.services import create_quotation, transition_quotation, convert_quotation_to_order, transition_order, convert_order_to_invoice, issue_invoice, invoice_profit
from billing.payments import register_payment, allocate_payment, create_installment_plan
from billing.ledger import current_balance
from billing.models import Quotation, Order, Invoice, Payment


class CommercialCycleEndToEndTests(TestCase):
    """One pass over the whole commercial chain with checked arithmetic.

    Deliberately a single test: the point is that the modules agree with each
    other end to end — stock cost feeds invoice profit, invoice issue feeds the
    ledger, allocation feeds the installment plan — which splitting into
    per-module tests would not prove. Per-module edge cases live beside it.
    """

    def test_stock_to_quotation_to_invoice_to_payment_keeps_every_total_consistent(self):
        mgr = User.objects.create_user(username="mgr", password="x", role=User.Role.SALES_MANAGER)
        cust = create_customer_with_phone(actor=mgr, full_name="آزمون", phone={"raw_phone": "09121234567", "is_primary": True})
        cat = create_product_category(actor=mgr, code="cat1", name="دسته")
        prod = create_product(actor=mgr, sku="SKU1", name="کالا", category=cat, current_price=Decimal("100.00"))
        wh = create_warehouse(actor=mgr, code="main", name="انبار مرکزی", is_default=True)
        record_stock_movement(actor=mgr, warehouse=wh, product=prod, movement_type=StockMovement.MovementType.OPENING, quantity=10, unit_cost=Decimal("60.00"))
        record_stock_movement(actor=mgr, warehouse=wh, product=prod, movement_type=StockMovement.MovementType.PURCHASE, quantity=10, unit_cost=Decimal("80.00"))
        item = StockItem.objects.get(warehouse=wh, product=prod)
        assert item.quantity == 20 and item.average_cost == Decimal("70.00"), item.average_cost

        q = create_quotation(actor=mgr, customer=cust, items=[{"product": prod, "quantity": 5, "discount_percent": Decimal("10")}], tax_rate=Decimal("9"))
        assert q.subtotal_amount == Decimal("450.00"), q.subtotal_amount
        assert q.tax_amount == Decimal("40.50"), q.tax_amount
        assert q.total_amount == Decimal("490.50"), q.total_amount

        transition_quotation(actor=mgr, quotation=q, to_status=Quotation.Status.SENT)
        q.refresh_from_db()
        transition_quotation(actor=mgr, quotation=q, to_status=Quotation.Status.ACCEPTED)
        q.refresh_from_db()
        # The order carries the warehouse now: approving it is what moves stock.
        order = convert_quotation_to_order(actor=mgr, quotation=q, warehouse=wh)
        assert order.total_amount == q.total_amount
        transition_order(actor=mgr, order=order, to_status=Order.Status.CONFIRMED)
        order.refresh_from_db()
        inv = convert_order_to_invoice(actor=mgr, order=order, warehouse=wh)
        inv = issue_invoice(actor=mgr, invoice=inv)
        item.refresh_from_db()
        assert item.quantity == 15
        assert invoice_profit(inv) == Decimal("100.00"), invoice_profit(inv)
        assert current_balance(cust) == Decimal("490.50")

        pay = register_payment(actor=mgr, customer=cust, method=Payment.Method.CASH, amount=Decimal("200.00"))
        allocate_payment(actor=mgr, payment=pay, invoice=inv)
        inv.refresh_from_db()
        assert inv.paid_amount == Decimal("200.00")
        assert current_balance(cust) == Decimal("290.50")

        plan = create_installment_plan(actor=mgr, invoice=inv, installment_count=3, start_date=date(2026, 9, 1))
        rows = list(plan.installments.order_by("sequence").values_list("sequence", "amount", "paid_amount", "status"))
        assert sum(r[1] for r in rows) == inv.total_amount

        cheque = register_payment(actor=mgr, customer=cust, method=Payment.Method.CHEQUE, amount=Decimal("90.50"),
                                  cheque={"bank_name": "ملت", "serial_number": "12345", "due_date": date(2026, 10, 1)})
        assert cheque.status == Payment.Status.PENDING
        assert current_balance(cust) == Decimal("290.50")
        from billing.payments import transition_cheque
        from billing.models import Cheque
        ch = Cheque.objects.get(payment=cheque)
        transition_cheque(actor=mgr, cheque=ch, to_status=Cheque.Status.DEPOSITED)
        ch.refresh_from_db()
        transition_cheque(actor=mgr, cheque=ch, to_status=Cheque.Status.CLEARED)
        cheque.refresh_from_db()
        assert cheque.status == Payment.Status.CONFIRMED
        assert current_balance(cust) == Decimal("200.00")
