from django.urls import path

from reports.views import SalesDocumentReportView, UserPerformanceDetailView, UserPerformanceExportView, UserPerformanceReportView


urlpatterns = [
    path("reports/user-performance/", UserPerformanceReportView.as_view(), name="user-performance-report"),
    path("reports/user-performance/details/", UserPerformanceDetailView.as_view(), name="user-performance-detail"),
    path("reports/sales-documents/", SalesDocumentReportView.as_view(), name="sales-document-report"),
    path("exports/user-performance.xlsx", UserPerformanceExportView.as_view(), name="user-performance-export"),
]
