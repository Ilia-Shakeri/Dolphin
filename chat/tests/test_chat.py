"""Chat: the service (start/send/mark-read), the object-scope selectors, and
the API surface, including the feature gate.
"""

from rest_framework.test import APIClient

from accounts.models import User
from chat import services
from chat.models import ChatMessage, ChatParticipant, ChatThread
from chat.selectors import is_participant, messages_for, threads_for, total_unread_count, unread_count_for
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from django.test import TestCase

PASSWORD = "Strong-pass-983!"


def without_internal_chat():
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) - frozenset({"internal_chat"}),
        source="signed-manifest",
    )


class ChatFixtures(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(username="chat.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.manager = User.objects.create_user(username="chat.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.other_agent = User.objects.create_user(username="chat.other", password=PASSWORD, role=User.Role.SALES_AGENT)


class ThreadServiceTests(ChatFixtures):
    def test_starting_a_thread_twice_returns_the_same_row(self):
        first = services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.manager.pk)
        second = services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.manager.pk)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ChatThread.objects.count(), 1)

    def test_starting_it_from_the_other_side_finds_the_same_thread(self):
        mine = services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.manager.pk)
        theirs = services.get_or_create_direct_thread(actor=self.manager, other_user_id=self.agent.pk)
        self.assertEqual(mine.pk, theirs.pk)

    def test_a_thread_has_exactly_two_participants(self):
        thread = services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.manager.pk)
        self.assertEqual(ChatParticipant.objects.filter(thread=thread).count(), 2)

    def test_a_user_cannot_start_a_thread_with_themselves(self):
        with self.assertRaises(BusinessRuleError):
            services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.agent.pk)

    def test_an_unknown_user_id_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            services.get_or_create_direct_thread(actor=self.agent, other_user_id=999999)

    def test_an_inactive_actor_is_refused(self):
        self.agent.is_active = False
        self.agent.save(update_fields=["is_active"])
        with self.assertRaises(BusinessPermissionDenied):
            services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.manager.pk)


class MessageServiceTests(ChatFixtures):
    def setUp(self):
        super().setUp()
        self.thread = services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.manager.pk)

    def test_sending_a_message_stores_it_and_bumps_the_thread(self):
        message = services.send_message(actor=self.agent, thread_id=self.thread.pk, body="سلام")
        self.assertEqual(message.body, "سلام")
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.last_message_at, message.created_at)

    def test_a_blank_message_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            services.send_message(actor=self.agent, thread_id=self.thread.pk, body="   ")

    def test_an_oversized_message_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            services.send_message(actor=self.agent, thread_id=self.thread.pk, body="x" * 4001)

    def test_a_non_participant_may_not_send_into_the_thread(self):
        with self.assertRaises(BusinessPermissionDenied):
            services.send_message(actor=self.other_agent, thread_id=self.thread.pk, body="سلام")

    def test_sending_advances_the_senders_own_read_cursor(self):
        services.send_message(actor=self.agent, thread_id=self.thread.pk, body="سلام")
        self.assertEqual(unread_count_for(self.agent, self.thread.pk), 0)

    def test_the_recipient_sees_it_as_unread_until_they_mark_it_read(self):
        services.send_message(actor=self.agent, thread_id=self.thread.pk, body="سلام")
        self.assertEqual(unread_count_for(self.manager, self.thread.pk), 1)
        services.mark_thread_read(actor=self.manager, thread_id=self.thread.pk)
        self.assertEqual(unread_count_for(self.manager, self.thread.pk), 0)

    def test_a_non_participant_may_not_mark_it_read(self):
        with self.assertRaises(BusinessPermissionDenied):
            services.mark_thread_read(actor=self.other_agent, thread_id=self.thread.pk)


class SelectorScopeTests(ChatFixtures):
    def setUp(self):
        super().setUp()
        self.thread = services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.manager.pk)
        services.send_message(actor=self.agent, thread_id=self.thread.pk, body="اول")
        services.send_message(actor=self.manager, thread_id=self.thread.pk, body="دوم")

    def test_both_participants_see_the_thread(self):
        self.assertIn(self.thread, threads_for(self.agent))
        self.assertIn(self.thread, threads_for(self.manager))

    def test_an_outsider_sees_nothing(self):
        self.assertNotIn(self.thread, threads_for(self.other_agent))
        self.assertFalse(is_participant(self.other_agent, self.thread.pk))

    def test_messages_for_an_outsider_is_empty(self):
        self.assertEqual(messages_for(self.other_agent, self.thread.pk).count(), 0)

    def test_messages_for_a_participant_returns_both_messages_in_order(self):
        bodies = list(messages_for(self.agent, self.thread.pk).values_list("body", flat=True))
        self.assertEqual(bodies, ["اول", "دوم"])

    def test_total_unread_count_excludes_my_own_messages(self):
        # The agent sent "اول" and read "دوم" is still sitting unread for them.
        self.assertEqual(total_unread_count(self.agent), 1)


class ChatAPITests(ChatFixtures):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_starting_reading_and_sending_over_http(self):
        self.client.force_authenticate(self.agent)
        started = self.client.post("/api/v1/chat/threads/", {"other_user_id": self.manager.pk}, format="json")
        self.assertEqual(started.status_code, 200)
        thread_id = started.data["id"]
        self.assertEqual(started.data["peer"]["id"], self.manager.pk)

        sent = self.client.post(f"/api/v1/chat/threads/{thread_id}/messages/", {"body": "سلام مدیر"}, format="json")
        self.assertEqual(sent.status_code, 201)
        self.assertTrue(sent.data["mine"])

        self.client.force_authenticate(self.manager)
        unread = self.client.get("/api/v1/chat/unread-count/")
        self.assertEqual(unread.data["count"], 1)

        messages = self.client.get(f"/api/v1/chat/threads/{thread_id}/messages/")
        self.assertEqual(messages.status_code, 200)
        self.assertEqual(len(messages.data), 1)
        self.assertEqual(messages.data[0]["body"], "سلام مدیر")
        self.assertFalse(messages.data[0]["mine"])

        # The GET above marked it read.
        unread_after = self.client.get("/api/v1/chat/unread-count/")
        self.assertEqual(unread_after.data["count"], 0)

    def test_the_thread_list_shows_the_peer_and_unread_count(self):
        thread = services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.manager.pk)
        services.send_message(actor=self.agent, thread_id=thread.pk, body="سلام")
        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/v1/chat/threads/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["peer"]["id"], self.agent.pk)
        self.assertEqual(response.data[0]["unread_count"], 1)
        self.assertEqual(response.data[0]["last_message_body"], "سلام")

    def test_colleagues_lists_everyone_but_myself(self):
        self.client.force_authenticate(self.agent)
        response = self.client.get("/api/v1/chat/colleagues/")
        ids = {row["id"] for row in response.data}
        self.assertNotIn(self.agent.pk, ids)
        self.assertIn(self.manager.pk, ids)
        self.assertIn(self.other_agent.pk, ids)

    def test_a_thread_outside_my_membership_is_404_not_403(self):
        thread = services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.manager.pk)
        self.client.force_authenticate(self.other_agent)
        response = self.client.get(f"/api/v1/chat/threads/{thread.pk}/messages/")
        self.assertEqual(response.status_code, 404)

    def test_sending_a_blank_message_is_a_400(self):
        thread = services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.manager.pk)
        self.client.force_authenticate(self.agent)
        response = self.client.post(f"/api/v1/chat/threads/{thread.pk}/messages/", {"body": "   "}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_starting_a_thread_with_myself_is_a_400(self):
        self.client.force_authenticate(self.agent)
        response = self.client.post("/api/v1/chat/threads/", {"other_user_id": self.agent.pk}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_every_chat_route_is_a_404_when_the_feature_is_off(self):
        self.client.force_authenticate(self.agent)
        with override_active_profile(without_internal_chat()):
            for path in (
                "/api/v1/chat/threads/",
                "/api/v1/chat/unread-count/",
                "/api/v1/chat/colleagues/",
            ):
                self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_the_read_endpoint_marks_the_thread_read_without_paging_messages(self):
        thread = services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.manager.pk)
        services.send_message(actor=self.agent, thread_id=thread.pk, body="سلام")
        self.client.force_authenticate(self.manager)
        response = self.client.post(f"/api/v1/chat/threads/{thread.pk}/read/")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(unread_count_for(self.manager, thread.pk), 0)

    def test_the_read_endpoint_is_404_for_a_non_participant(self):
        thread = services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.manager.pk)
        self.client.force_authenticate(self.other_agent)
        response = self.client.post(f"/api/v1/chat/threads/{thread.pk}/read/")
        self.assertEqual(response.status_code, 404)

    def test_polling_with_after_id_returns_only_newer_messages_and_does_not_mark_read(self):
        thread = services.get_or_create_direct_thread(actor=self.agent, other_user_id=self.manager.pk)
        first = services.send_message(actor=self.agent, thread_id=thread.pk, body="اول")
        services.send_message(actor=self.agent, thread_id=thread.pk, body="دوم")
        self.client.force_authenticate(self.manager)
        response = self.client.get(f"/api/v1/chat/threads/{thread.pk}/messages/?after_id={first.pk}")
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["body"], "دوم")
        self.assertEqual(unread_count_for(self.manager, thread.pk), 2)
