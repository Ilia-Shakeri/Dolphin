from django.urls import path

from reports.views import UserPerformanceExportView, UserPerformanceReportView


urlpatterns = [
    path("reports/user-performance/", UserPerformanceReportView.as_view(), name="user-performance-report"),
    path("exports/user-performance.xlsx", UserPerformanceExportView.as_view(), name="user-performance-export"),
]
