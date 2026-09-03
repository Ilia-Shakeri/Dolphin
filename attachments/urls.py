from django.urls import path

from attachments.views import AttachmentDeleteView, AttachmentDownloadView, AttachmentListUploadView


urlpatterns = [
    path("attachments/", AttachmentListUploadView.as_view(), name="attachments-list-upload"),
    path("attachments/<int:attachment_id>/download/", AttachmentDownloadView.as_view(), name="attachment-download"),
    path("attachments/<int:attachment_id>/delete/", AttachmentDeleteView.as_view(), name="attachment-delete"),
]
