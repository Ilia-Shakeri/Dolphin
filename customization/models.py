"""Personalization (2.40.53, owner decision 2026-10-14, Q18).

«همگی نیاز است چه بسا بیشتر. بیشتر فیلدهای پنل باید قابلیت شخصی‌سازی داشته
باشند. شخصی‌سازی هم فیچر است و باید فعال شود.»

A company's own fields on its records. Each `CustomFieldDefinition` names one
field of one entity; the value lives on the record itself, in its
`custom_fields` JSON column, keyed by the definition's `key` and always stored
as text. Turning the `customization` feature off hides every field and keeps
every value; deactivating a definition hides that field and keeps its values.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel

LABEL_MAX_LENGTH = 80
MAX_CHOICES = 50
CHOICE_MAX_LENGTH = 80
#: Most fields one entity may carry: a form of hundreds is not a form.
MAX_FIELDS_PER_ENTITY = 40


class CustomFieldDefinition(TimeStampedModel):
    class Entity(models.TextChoices):
        CUSTOMER = "customer", "مشتری"

    class FieldType(models.TextChoices):
        TEXT = "text", "متن کوتاه"
        LONG_TEXT = "long_text", "متن بلند"
        NUMBER = "number", "عدد"
        DATE = "date", "تاریخ"
        CHOICE = "choice", "انتخاب از فهرست"
        BOOLEAN = "boolean", "بله یا خیر"

    entity = models.CharField(max_length=20, choices=Entity.choices)
    #: Made by the service (`cf_<n>`), never typed: a label may change, the key
    #: the stored values hang on may not.
    key = models.CharField(max_length=40)
    label = models.CharField(max_length=LABEL_MAX_LENGTH)
    field_type = models.CharField(max_length=12, choices=FieldType.choices)
    choices = models.JSONField(default=list, blank=True)
    required = models.BooleanField(default=False)
    show_in_list = models.BooleanField(default=False)
    filterable = models.BooleanField(default=False)
    searchable = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["entity", "position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["entity", "key"], name="uniq_custom_field_key"),
            models.CheckConstraint(condition=Q(entity__in=["customer"]), name="custom_field_entity_valid"),
            models.CheckConstraint(
                condition=Q(field_type__in=["text", "long_text", "number", "date", "choice", "boolean"]),
                name="custom_field_type_valid",
            ),
            models.CheckConstraint(condition=Q(key__regex=r"\Acf_[0-9]{1,6}\Z"), name="custom_field_key_shape"),
            models.CheckConstraint(condition=Q(label__regex=r"\S"), name="custom_field_label_nonblank"),
        ]


#: A saved list view (2.40.54): which page, and the filter form as it stood.
VIEW_NAME_MAX_LENGTH = 60
MAX_VIEWS_PER_PAGE = 30


class SavedView(TimeStampedModel):
    """A list page's filters, saved under a name (2.40.54, feature
    `customization`, owner decision 2026-10-14: «نماهای ذخیره‌شدهٔ جدول، شخصی
    یا تیمی»).

    `page` names the list (`<data-page>:<filter form id>`); `state` is the
    filter form's fields by id, as text, applied back as they were. Personal
    by default; `shared` shows it to everyone who opens that page, which needs
    `views.share`. A person's own setting: it may be deleted.
    """

    page = models.CharField(max_length=110)
    name = models.CharField(max_length=VIEW_NAME_MAX_LENGTH)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="saved_views")
    shared = models.BooleanField(default=False)
    state = models.JSONField(default=dict)

    class Meta:
        ordering = ["page", "name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "page", "name"], name="uniq_saved_view_name"),
            models.CheckConstraint(condition=Q(name__regex=r"\S"), name="saved_view_name_nonblank"),
            models.CheckConstraint(
                condition=Q(page__regex=r"\A[a-z0-9-]{1,40}:[a-z0-9-]{1,60}\Z"), name="saved_view_page_shape"
            ),
        ]
        indexes = [models.Index(fields=["page", "shared"])]
