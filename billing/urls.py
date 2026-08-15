from rest_framework.routers import DefaultRouter

from billing.views import (
    ChequeViewSet,
    CustomerLedgerViewSet,
    InstallmentPlanViewSet,
    InstallmentViewSet,
    InvoiceViewSet,
    OrderViewSet,
    PaymentAllocationViewSet,
    PaymentViewSet,
    QuotationViewSet,
)


router = DefaultRouter()
router.register("quotations", QuotationViewSet, basename="quotation")
router.register("orders", OrderViewSet, basename="order")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("payments", PaymentViewSet, basename="payment")
router.register("payment-allocations", PaymentAllocationViewSet, basename="payment-allocation")
router.register("cheques", ChequeViewSet, basename="cheque")
router.register("installment-plans", InstallmentPlanViewSet, basename="installment-plan")
router.register("installments", InstallmentViewSet, basename="installment")
router.register("customer-ledger", CustomerLedgerViewSet, basename="customer-ledger")
urlpatterns = router.urls
