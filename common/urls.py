from django.urls import path, re_path

from common.backup_views import BackupDownloadView, BackupListView, BackupRestoreView
from common.branding_views import BrandLogoView, BrandSettingsView
from common.dashboard_layout_views import DashboardLayoutView
from common.dashboard_views import DashboardView
from common.preferences_views import UserPreferenceView
from common.reminders_views import ReminderCountView, ReminderListView
from common.search_views import GlobalSearchView
from common.timeline_views import CustomerTimelineView


urlpatterns = [
    path("backups/", BackupListView.as_view(), name="backups-api"),
    # The archive name is matched by the router, not only by the view: this
    # is character for character the shape `scripts/backup-postgres.sh`
    # produces, so a name that could leave the backup directory is a 404
    # before any Python runs. `common.backups` checks it again anyway.
    re_path(
        r"^backups/download/(?P<name>dolphin-pg-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}\.dump)$",
        BackupDownloadView.as_view(),
        name="backup-download-api",
    ),
    path("backups/restore/", BackupRestoreView.as_view(), name="backup-restore-api"),
    path("branding/", BrandSettingsView.as_view(), name="branding-settings-api"),
    path("branding/logo/", BrandLogoView.as_view(), name="branding-logo"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("dashboard-layout/", DashboardLayoutView.as_view(), name="dashboard-layout-api"),
    path("preferences/", UserPreferenceView.as_view(), name="user-preferences-api"),
    path("reminders/", ReminderListView.as_view(), name="reminders"),
    path("reminders/count/", ReminderCountView.as_view(), name="reminders-count"),
    path("search/", GlobalSearchView.as_view(), name="global-search"),
    path(
        "customers/<int:customer_id>/timeline/",
        CustomerTimelineView.as_view(),
        name="customer-timeline",
    ),
]
