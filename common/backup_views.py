"""`/api/v1/backups/` — list, download, request a backup, request a restore.

Platform Admin only and feature-gated on `panel_backup`, both enforced in
`common.backups` rather than only here, so a second caller cannot reach the
service layer without them. 404-not-403 when the feature is off, the same
shape `/api/v1/branding/` uses: a deployment that never turned this on shows
no evidence the endpoint exists.

Read `common/backups.py` before changing anything here. In short: none of
these endpoints touch the database's structure. They read a directory, they
stream a file, and they write a request that a separate privileged
container acts on — because the web container is deliberately unable to do
more than that.
"""

from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from common import backups
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessRuleError
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import IsPlatformAdmin
from common.throttles import SensitiveRateThrottle

#: The phrase an admin has to type to restore.
#:
#: Typed, not ticked. A checkbox beside a destructive action is dismissed by
#: the same reflex that clicks the button; typing the word is a second,
#: deliberate act — and it is the control the runbook's own disaster-restore
#: section already asks for in prose ("with the customer's explicit
#: go-ahead"). Persian, and short enough to type without copy-paste.
RESTORE_CONFIRMATION = "بازگردانی"


class BackupFeatureMixin:
    required_feature = "panel_backup"
    permission_classes = [IsPlatformAdmin]
    throttle_classes = [SensitiveRateThrottle]

    def initial(self, request, *args, **kwargs):
        if not feature_enabled(self.required_feature):
            raise NotFound()
        super().initial(request, *args, **kwargs)


def _job_row(job):
    return {
        "token": job.token,
        "kind": job.kind,
        "kind_display": job.get_kind_display(),
        "status": job.status,
        "status_display": job.get_status_display(),
        "requested_at": job.created_at,
        "requested_by": getattr(job.requested_by, "username", ""),
        "original_filename": job.original_filename,
        "size_bytes": job.size_bytes,
        "archive_name": job.archive_name,
        "message": job.message,
        "finished_at": job.finished_at,
    }


class BackupListView(BackupFeatureMixin, APIView):
    """GET the archives on the backup volume plus the recent job history;
    POST asks the agent to take a new backup now.
    """

    @extend_schema(
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description=(
            "Database backups available to this deployment, newest first, and the last ten "
            "backup/restore requests made from the panel with whatever the agent reported back."
        ),
    )
    def get(self, request):
        try:
            archives = backups.list_backups(actor=request.user)
        except backups.BackupsUnavailable as error:
            # Not a 400: there is nothing the caller can correct. The panel
            # renders this as "the backup volume is not available on this
            # deployment", which is the actual situation.
            response = Response({"available": False, "detail": error.detail, "archives": [], "jobs": []})
            response["Cache-Control"] = "private, no-store"
            return response
        response = Response({
            "available": True,
            "archives": archives,
            "jobs": [_job_row(job) for job in backups.recent_jobs(actor=request.user)],
        })
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request=None,
        responses={
            202: {"type": "object"},
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Asks the backup agent to take a backup now. Returns immediately with the job token; "
            "the work happens in the agent container and its outcome appears in the job list."
        ),
    )
    def post(self, request):
        job = backups.request_backup(actor=request.user)
        response = Response(_job_row(job), status=202)
        response["Cache-Control"] = "private, no-store"
        return response


class BackupDownloadView(BackupFeatureMixin, APIView):
    """One archive, streamed.

    Streamed rather than read: a dump is hundreds of megabytes and the web
    container has a memory limit that a single `read()` would exceed.
    """

    @extend_schema(
        responses={200: {"type": "string", "format": "binary"}, 403: ACCESS_DENIED_RESPONSE},
        description="Downloads one backup archive by its exact name.",
    )
    def get(self, request, name):
        handle, size = backups.open_backup(actor=request.user, name=name)
        # `FileResponse` rather than `HttpResponse(bytes(...))`, which is
        # what `AttachmentDownloadView` can afford: an attachment is capped
        # at 10 MB and a dump is not capped at all. This one streams in
        # blocks and closes the handle when the response finishes.
        response = FileResponse(handle, content_type="application/octet-stream")
        response["Content-Length"] = str(size)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        # The name came out of `ARCHIVE_NAME`, so it holds nothing a header
        # could be split on — quoted anyway, for the same reason
        # `attachments/views.py` strips a quote from a name it did not
        # generate: a download header is not the place to rely on one
        # upstream check.
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response


class BackupRestoreView(BackupFeatureMixin, APIView):
    """Upload a dump and ask the agent to restore it over the live database.

    The most consequential endpoint in this product. What it does *not* do
    is as important as what it does: it does not restore anything. It writes
    the upload and a request into the spool volume, and returns. If the
    agent is not running, the job stays visible as waiting and then expires
    — the panel never reports a restore that did not happen.
    """

    parser_classes = [MultiPartParser]

    @extend_schema(
        request={"multipart/form-data": {"type": "object", "properties": {
            "archive": {"type": "string", "format": "binary"},
            "confirm": {"type": "string"},
        }}},
        responses={
            202: {"type": "object"},
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Uploads a custom-format PostgreSQL dump and asks the backup agent to restore it over "
            "the live database, replacing every row written since that dump was taken. Requires the "
            "exact confirmation phrase, and the agent takes a safety backup of the current database "
            "before it replaces anything."
        ),
    )
    def post(self, request):
        upload = request.FILES.get("archive")
        if upload is None:
            raise BusinessRuleError({"archive": "فایل پشتیبان را انتخاب کنید."})
        if str(request.data.get("confirm", "")).strip() != RESTORE_CONFIRMATION:
            raise BusinessRuleError({
                "confirm": f"برای تأیید، عبارت «{RESTORE_CONFIRMATION}» را دقیقاً وارد کنید.",
            })
        job = backups.request_restore(
            actor=request.user, upload=upload, original_filename=getattr(upload, "name", ""),
        )
        response = Response(_job_row(job), status=202)
        response["Cache-Control"] = "private, no-store"
        return response
