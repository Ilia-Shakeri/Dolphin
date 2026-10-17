from django.urls import path
from rest_framework.routers import DefaultRouter

from aftersales.settings_views import (
    AfterSalesSettingsView,
    CalendarView,
    CaseStageDetailView,
    CaseStageListView,
    CaseStageMoveView,
    CaseTypeDetailView,
    CaseTypeListView,
    CaseTypeStagesView,
    FixedHolidaysView,
    HolidayDetailView,
    HolidayListView,
    SlaPolicyView,
)
from aftersales.views import AfterSalesRequestViewSet


router = DefaultRouter()
router.register("after-sales", AfterSalesRequestViewSet, basename="after-sales")
urlpatterns = [
    # Case types, stages, deadlines and the working calendar (2.40.60).
    path("after-sales-settings/", AfterSalesSettingsView.as_view(), name="after-sales-settings"),
    path("after-sales-settings/types/", CaseTypeListView.as_view(), name="after-sales-types"),
    path("after-sales-settings/types/<int:pk>/", CaseTypeDetailView.as_view(), name="after-sales-type"),
    path("after-sales-settings/types/<int:pk>/stages/", CaseTypeStagesView.as_view(), name="after-sales-type-stages"),
    path("after-sales-settings/stages/", CaseStageListView.as_view(), name="after-sales-stages"),
    path("after-sales-settings/stages/<int:pk>/", CaseStageDetailView.as_view(), name="after-sales-stage"),
    path("after-sales-settings/stages/<int:pk>/move/", CaseStageMoveView.as_view(), name="after-sales-stage-move"),
    path("after-sales-settings/sla/", SlaPolicyView.as_view(), name="after-sales-sla"),
    path("after-sales-settings/calendar/", CalendarView.as_view(), name="after-sales-calendar"),
    path("after-sales-settings/holidays/", HolidayListView.as_view(), name="after-sales-holidays"),
    path("after-sales-settings/holidays/<int:pk>/", HolidayDetailView.as_view(), name="after-sales-holiday"),
    path("after-sales-settings/holidays/fixed/", FixedHolidaysView.as_view(), name="after-sales-holidays-fixed"),
    *router.urls,
]
