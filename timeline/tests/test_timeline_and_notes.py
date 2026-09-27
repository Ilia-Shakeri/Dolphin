"""The recorded timeline and profile notes (2.20.0).

* recording is idempotent on `(source, source_ref, kind)`;
* recorded events merge into both timeline endpoints, newest first;
* a note is read with `notes.read`, written with `notes.write`, edited only
  by its author, and deleted only by the Platform Admin or a holder of
  `notes.delete` — on a profile the actor can open, and never otherwise.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User, UserCapabilityOverride
from auditlog.models import ActivityLog
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from sales.services import create_customer_with_phone
from timeline.models import PersonNote, TimelineEntry
from timeline.services import record

PASSWORD = "Strong-pass-448!"


def profile_without(*features):
    return DeploymentProfile(
        profile_id="client-1", features=frozenset(ALL_FEATURES) - frozenset(features), source="signed-manifest"
    )


class Fixtures(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="tn.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="tn.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="tn.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری یادداشت", phone={"raw_phone": "09150001111", "is_primary": True}
        )

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def notes_url(self, person_type="customer", person_id=None):
        return f"/api/v1/profiles/{person_type}/{person_id or self.customer.pk}/notes/"


class RecordTests(Fixtures):
    def test_recording_the_same_event_twice_keeps_one_entry(self):
        for _ in range(2):
            record(person_type="customer", person_id=self.customer.pk, kind="call", title="تماس", source="test", source_ref="42")
        self.assertEqual(TimelineEntry.objects.filter(source="test", source_ref="42").count(), 1)

    def test_an_unknown_person_type_is_refused(self):
        with self.assertRaises(ValueError):
            record(person_type="supplier", person_id=1, kind="call", title="تماس", source="test")

    def test_recorded_events_join_both_timeline_endpoints(self):
        record(person_type="customer", person_id=self.customer.pk, kind="call", title="تماس ضبط‌شده", source="test", source_ref="1")
        unified = self.api(self.manager).get(f"/api/v1/profiles/customer/{self.customer.pk}/timeline/").data
        legacy = self.api(self.manager).get(f"/api/v1/customers/{self.customer.pk}/timeline/").data
        self.assertEqual(unified, legacy)
        self.assertIn("تماس ضبط‌شده", [event["title"] for event in unified["events"]])

    def test_an_entry_needing_a_capability_is_hidden_without_it(self):
        record(
            person_type="customer", person_id=self.customer.pk, kind="call", title="فقط مدیران",
            source="test", source_ref="2", required_capability="payments.company",
        )
        manager_titles = [e["title"] for e in self.api(self.manager).get(f"/api/v1/profiles/customer/{self.customer.pk}/timeline/").data["events"]]
        self.assertIn("فقط مدیران", manager_titles)
        mine = create_customer_with_phone(actor=self.agent, full_name="مشتری بازاریاب", phone={"raw_phone": "09150001112", "is_primary": True})
        record(
            person_type="customer", person_id=mine.pk, kind="call", title="پنهان از بازاریاب",
            source="test", source_ref="3", required_capability="payments.company",
        )
        agent_titles = [e["title"] for e in self.api(self.agent).get(f"/api/v1/profiles/customer/{mine.pk}/timeline/").data["events"]]
        self.assertNotIn("پنهان از بازاریاب", agent_titles)


class NoteTests(Fixtures):
    def test_a_manager_adds_and_lists_a_note_and_it_reaches_the_timeline(self):
        response = self.api(self.manager).post(self.notes_url(), {"body": "  جلسه خوب بود\nقرار بعدی شنبه  "}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["body"], "جلسه خوب بود\nقرار بعدی شنبه")
        self.assertTrue(response.data["can_edit"])
        listing = self.api(self.manager).get(self.notes_url()).data
        self.assertEqual(listing["count"], 1)
        events = self.api(self.manager).get(f"/api/v1/profiles/customer/{self.customer.pk}/timeline/").data["events"]
        self.assertEqual(events[0]["kind"], "note")
        self.assertEqual(events[0]["title"], "جلسه خوب بود")
        self.assertTrue(ActivityLog.objects.filter(operation="person_note.created").exists())

    def test_a_blank_note_is_refused(self):
        self.assertEqual(self.api(self.manager).post(self.notes_url(), {"body": "   "}, format="json").status_code, 400)

    def test_only_the_author_edits(self):
        note = self.api(self.manager).post(self.notes_url(), {"body": "متن"}, format="json").data
        self.assertEqual(self.api(self.admin).patch(f"/api/v1/person-notes/{note['id']}/", {"body": "دیگری"}, format="json").status_code, 403)
        edited = self.api(self.manager).patch(f"/api/v1/person-notes/{note['id']}/", {"body": "متن تازه"}, format="json")
        self.assertEqual(edited.status_code, 200)
        entry = TimelineEntry.objects.get(source="notes", source_ref=str(note["id"]))
        self.assertEqual(entry.body, "متن تازه")

    def test_deletion_follows_the_delete_permission_rule(self):
        note = self.api(self.manager).post(self.notes_url(), {"body": "حذف‌شدنی"}, format="json").data
        url = f"/api/v1/person-notes/{note['id']}/"
        self.assertEqual(self.api(self.manager).delete(url).status_code, 403)
        UserCapabilityOverride.objects.create(user=self.manager, capability="notes.delete", granted=True)
        self.assertEqual(self.api(self.manager).delete(url).status_code, 204)
        self.assertFalse(PersonNote.objects.filter(pk=note["id"]).exists())
        self.assertFalse(TimelineEntry.objects.filter(source="notes", source_ref=str(note["id"])).exists())

    def test_the_platform_admin_deletes_any_note(self):
        note = self.api(self.manager).post(self.notes_url(), {"body": "حذف‌شدنی"}, format="json").data
        self.assertEqual(self.api(self.admin).delete(f"/api/v1/person-notes/{note['id']}/").status_code, 204)

    def test_a_person_outside_scope_is_a_404_for_reading_and_writing(self):
        self.assertEqual(self.api(self.agent).get(self.notes_url()).status_code, 404)
        self.assertEqual(self.api(self.agent).post(self.notes_url(), {"body": "x"}, format="json").status_code, 404)
        note = self.api(self.manager).post(self.notes_url(), {"body": "خصوصی"}, format="json").data
        self.assertEqual(self.api(self.agent).patch(f"/api/v1/person-notes/{note['id']}/", {"body": "y"}, format="json").status_code, 404)

    def test_a_colleague_can_carry_notes_too(self):
        response = self.api(self.manager).post(self.notes_url("user", self.agent.pk), {"body": "پیگیری خوب"}, format="json")
        self.assertEqual(response.status_code, 201)
        # The person themselves reads what is written on their profile.
        self.assertEqual(self.api(self.agent).get(self.notes_url("user", self.agent.pk)).data["count"], 1)

    def test_without_the_feature_there_are_no_notes_anywhere(self):
        self.api(self.manager).post(self.notes_url(), {"body": "قبل از خاموش شدن"}, format="json")
        with override_active_profile(profile_without("person_notes")):
            self.assertEqual(self.api(self.manager).get(self.notes_url()).status_code, 404)
            events = self.api(self.manager).get(f"/api/v1/profiles/customer/{self.customer.pk}/timeline/").data["events"]
            self.assertNotIn("note", [event["kind"] for event in events])
        # Switching the feature off deleted nothing.
        self.assertEqual(PersonNote.objects.count(), 1)

    def test_the_writing_capability_can_be_revoked_per_user(self):
        UserCapabilityOverride.objects.create(user=self.manager, capability="notes.write", granted=False)
        self.assertEqual(self.api(self.manager).post(self.notes_url(), {"body": "x"}, format="json").status_code, 403)
