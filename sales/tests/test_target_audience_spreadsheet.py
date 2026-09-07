"""The target-audience round trip: export a campaign, write on the file, upload it back.

Same shape as `test_product_spreadsheet.py`. The first test proves the export
is a file the import understands without ever hand-building a sheet; the rest
pin the three outcomes a marketer is told about — created, duplicate, invalid —
and that identity is scoped to one campaign, not global.
"""

import io

from django.test import TestCase
from openpyxl import Workbook, load_workbook
from rest_framework.test import APIClient

from accounts.models import User
from common.exceptions import BusinessRuleError
from reports.xlsx import TARGET_AUDIENCE_HEADERS
from sales.models import TargetAudienceMember
from sales.services import add_target_audience_member, create_customer_with_phone, create_lead, reassign_lead
from sales.target_audience_imports import import_target_audience_from_workbook


PASSWORD = "Strong-pass-937!"


def sheet_from(*rows, headers=TARGET_AUDIENCE_HEADERS):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return stream


def row(full_name, raw_phone, *, notes=""):
    """A row in TARGET_AUDIENCE_HEADERS order, with `id`/`status` blank — an import ignores both."""
    return ("", full_name, raw_phone, "", notes)


class TargetAudienceSpreadsheetTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="ta.sheet.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="ta.sheet.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری کمپین", phone={"raw_phone": "09120009999", "is_primary": True}
        )
        self.lead = create_lead(actor=self.manager, customer=customer, source="manual")
        self.other_lead = create_lead(actor=self.manager, customer=customer, source="manual")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    # --- the round trip ------------------------------------------------------

    def test_an_export_is_a_file_the_import_understands(self):
        add_target_audience_member(
            actor=self.manager, lead=self.lead, full_name="نفر اول", raw_phone="09121110001",
        )
        response = self.client_for(self.manager).get(
            f"/api/v1/exports/target-audience.xlsx?lead={self.lead.pk}"
        )
        self.assertEqual(response.status_code, 200)

        # Write one new row onto the exported file, exactly as a marketer would.
        workbook = load_workbook(io.BytesIO(response.content))
        sheet = workbook.active
        sheet.append(("", "نفر دوم", "09121110002", "", ""))
        stream = io.BytesIO()
        workbook.save(stream)
        stream.seek(0)

        result = import_target_audience_from_workbook(actor=self.manager, lead=self.lead, stream=stream)

        # The exported row comes back as a duplicate — never a second identity.
        self.assertEqual(result.created, 1)
        self.assertEqual(result.duplicates, 1)
        self.assertEqual(result.invalid, 0)
        self.assertEqual(TargetAudienceMember.objects.filter(lead=self.lead).count(), 2)
        self.assertTrue(
            TargetAudienceMember.objects.filter(lead=self.lead, full_name="نفر دوم").exists()
        )

    # --- duplicates ------------------------------------------------------------

    def test_a_duplicate_phone_in_the_same_campaign_is_counted_and_never_overwrites(self):
        add_target_audience_member(
            actor=self.manager, lead=self.lead, full_name="نام اصلی", raw_phone="09121110003",
        )
        result = import_target_audience_from_workbook(
            actor=self.manager, lead=self.lead, stream=sheet_from(row("نام تازه", "09121110003")),
        )
        self.assertEqual(result.created, 0)
        self.assertEqual(result.duplicates, 1)
        existing = TargetAudienceMember.objects.get(lead=self.lead, normalized_phone="+989121110003")
        self.assertEqual(existing.full_name, "نام اصلی")

    def test_a_phone_already_in_another_campaign_is_a_duplicate_here_too(self):
        """Identity is the phone number, global across every campaign — not per lead."""
        add_target_audience_member(
            actor=self.manager, lead=self.other_lead, full_name="در کمپین دیگر", raw_phone="09121110004",
        )
        result = import_target_audience_from_workbook(
            actor=self.manager, lead=self.lead, stream=sheet_from(row("در این کمپین", "09121110004")),
        )
        self.assertEqual(result.created, 0)
        self.assertEqual(result.duplicates, 1)
        self.assertEqual(TargetAudienceMember.objects.filter(lead=self.lead).count(), 0)
        self.assertTrue(TargetAudienceMember.objects.filter(lead=self.other_lead, full_name="در کمپین دیگر").exists())

    def test_a_phone_repeated_inside_one_file_is_imported_once(self):
        result = import_target_audience_from_workbook(
            actor=self.manager,
            lead=self.lead,
            stream=sheet_from(row("یک", "09121110005"), row("دو", "09121110005")),
        )
        self.assertEqual(result.created, 1)
        self.assertEqual(result.duplicates, 1)
        self.assertEqual(
            TargetAudienceMember.objects.get(lead=self.lead, normalized_phone="+989121110005").full_name,
            "یک",
        )

    # --- rows that cannot become an identity ------------------------------------

    def test_an_invalid_row_is_reported_and_the_rest_still_import(self):
        result = import_target_audience_from_workbook(
            actor=self.manager,
            lead=self.lead,
            stream=sheet_from(
                row("خوب", "09121110006"),
                row("", "09121110007"),
                row("بدون تلفن", ""),
                row("تلفن خراب", "12345"),
                row("خوب دوم", "09121110008"),
            ),
        )
        self.assertEqual(result.created, 2)
        self.assertEqual(result.invalid, 3)
        self.assertEqual(
            sorted(TargetAudienceMember.objects.filter(lead=self.lead).values_list("full_name", flat=True)),
            ["خوب", "خوب دوم"],
        )
        self.assertEqual([entry["row"] for entry in result.errors], [3, 4, 5])

    def test_a_blank_row_is_skipped_without_being_called_invalid(self):
        result = import_target_audience_from_workbook(
            actor=self.manager,
            lead=self.lead,
            stream=sheet_from(row("ب۱", "09121110009"), (None,) * 5, row("ب۲", "09121110010")),
        )
        self.assertEqual(result.created, 2)
        self.assertEqual(result.invalid, 0)

    def test_a_sheet_that_is_not_ours_is_refused_rather_than_read_positionally(self):
        with self.assertRaises(BusinessRuleError):
            import_target_audience_from_workbook(
                actor=self.manager,
                lead=self.lead,
                stream=sheet_from(("x", "y", "z"), headers=("alpha", "beta", "gamma")),
            )
        self.assertEqual(TargetAudienceMember.objects.filter(lead=self.lead).count(), 0)

    def test_columns_may_be_reordered_because_they_match_by_name(self):
        headers = ("raw_phone", "full_name")
        result = import_target_audience_from_workbook(
            actor=self.manager, lead=self.lead, stream=sheet_from(("09121110011", "جابه‌جا"), headers=headers),
        )
        self.assertEqual(result.created, 1)
        self.assertEqual(
            TargetAudienceMember.objects.get(lead=self.lead, normalized_phone="+989121110011").full_name,
            "جابه‌جا",
        )

    def test_a_file_that_is_not_a_spreadsheet_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            import_target_audience_from_workbook(
                actor=self.manager, lead=self.lead, stream=io.BytesIO(b"not a workbook at all")
            )

    # --- authorisation -----------------------------------------------------

    def test_a_marketer_cannot_import_a_target_audience(self):
        """Frontend hiding is not authorisation; the endpoint refuses too.

        Assigned to the agent, so this is the service-level write refusal
        (`_require_target_audience_editor`), not merely the lead being outside
        their read scope.
        """
        reassign_lead(actor=self.manager, lead=self.lead, to_user=self.agent)
        upload = sheet_from(row("مهم نیست", "09121110012"))
        upload.name = "audience.xlsx"
        response = self.client_for(self.agent).post(
            "/api/v1/target-audience/import-xlsx/",
            {"file": upload, "lead": self.lead.pk},
            format="multipart",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(TargetAudienceMember.objects.filter(lead=self.lead).count(), 0)

    def test_the_endpoint_refuses_anything_that_is_not_an_xlsx(self):
        response = self.client_for(self.manager).post(
            "/api/v1/target-audience/import-xlsx/",
            {"file": io.BytesIO(b"full_name,raw_phone\nA,09120000000"), "lead": self.lead.pk},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_the_endpoint_refuses_a_lead_outside_the_caller_scope(self):
        outsider = User.objects.create_user(
            username="ta.sheet.outsider", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        upload = sheet_from(row("مهم نیست", "09121110013"))
        upload.name = "audience.xlsx"
        response = self.client_for(outsider).post(
            "/api/v1/target-audience/import-xlsx/",
            {"file": upload, "lead": self.lead.pk},
            format="multipart",
        )
        self.assertIn(response.status_code, (403, 404))
        self.assertEqual(TargetAudienceMember.objects.filter(lead=self.lead).count(), 0)

    def test_the_endpoint_reports_all_three_counts(self):
        add_target_audience_member(
            actor=self.manager, lead=self.lead, full_name="موجود", raw_phone="09121110014",
        )
        upload = sheet_from(
            row("تکراری", "09121110014"),
            row("تازه", "09121110015"),
            row("خراب", "بد"),
        )
        upload.name = "audience.xlsx"
        response = self.client_for(self.manager).post(
            "/api/v1/target-audience/import-xlsx/",
            {"file": upload, "lead": self.lead.pk},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(response.data["duplicates"], 1)
        self.assertEqual(response.data["invalid"], 1)

    def test_an_agent_may_still_export_the_audience_of_their_own_campaign(self):
        reassign_lead(actor=self.manager, lead=self.lead, to_user=self.agent)
        add_target_audience_member(
            actor=self.manager, lead=self.lead, full_name="نفر", raw_phone="09121110016",
        )
        response = self.client_for(self.agent).get(
            f"/api/v1/exports/target-audience.xlsx?lead={self.lead.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        sheet = load_workbook(io.BytesIO(response.content)).active
        rows = list(sheet.iter_rows(values_only=True))
        self.assertEqual(rows[0], TARGET_AUDIENCE_HEADERS)
        self.assertEqual(rows[1][rows[0].index("full_name")], "نفر")
