from django.urls import path

from reports.customer_views import (
    CustomerCityReportView,
    CustomerGrowthReportView,
    ListChartView,
)
from reports.directory_views import (
    CustomerDirectoryExportView,
    ProductCatalogueExportView,
    UserDirectoryExportView,
)

from reports.financial_views import (
    InventoryValuationExportView,
    InventoryValuationReportView,
    ProfitExportView,
    ProfitReportView,
    ReceivablesExportView,
    ReceivablesReportView,
)
from reports.views import SalesDocumentReportView, UserPerformanceDetailView, UserPerformanceExportView, UserPerformanceReportView


urlpatterns = [
    path("reports/list-chart/<slug:key>/", ListChartView.as_view(), name="list-chart"),
    path("reports/customer-cities/", CustomerCityReportView.as_view(), name="customer-city-report"),
    path("reports/customer-growth/", CustomerGrowthReportView.as_view(), name="customer-growth-report"),
    path("reports/user-performance/", UserPerformanceReportView.as_view(), name="user-performance-report"),
    path("reports/user-performance/details/", UserPerformanceDetailView.as_view(), name="user-performance-detail"),
    path("reports/sales-documents/", SalesDocumentReportView.as_view(), name="sales-document-report"),
    path("reports/receivables/", ReceivablesReportView.as_view(), name="receivables-report"),
    path("reports/profit/", ProfitReportView.as_view(), name="profit-report"),
    path("reports/stock-valuation/", InventoryValuationReportView.as_view(), name="stock-valuation-report"),
    path("exports/user-performance.xlsx", UserPerformanceExportView.as_view(), name="user-performance-export"),
    path("exports/users.xlsx", UserDirectoryExportView.as_view(), name="user-directory-export"),
    path("exports/customers.xlsx", CustomerDirectoryExportView.as_view(), name="customer-directory-export"),
    path("exports/products.xlsx", ProductCatalogueExportView.as_view(), name="product-catalogue-export"),
    path("exports/receivables.xlsx", ReceivablesExportView.as_view(), name="receivables-export"),
    path("exports/profit.xlsx", ProfitExportView.as_view(), name="profit-export"),
    path("exports/stock-valuation.xlsx", InventoryValuationExportView.as_view(), name="stock-valuation-export"),
]
