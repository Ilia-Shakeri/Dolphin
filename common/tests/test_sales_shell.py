import re
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from common.throttles import SensitiveRateThrottle
from sales.models import Interaction
from sales.services import (
    assign_lead,
    create_customer_with_phone,
    create_lead,
    record_interaction,
    register_sales_document,
)


ROOT = Path(__file__).resolve().parents[2]


class SalesShellContractTests(SimpleTestCase):
    def test_client_covers_all_required_pages_and_states(self):
        script = (ROOT / "common" / "static" / "common" / "forooshbin-app.js").read_text(encoding="utf-8")
        for page in ("customers", "customer-detail", "leads", "lead-detail", "interactions", "interaction-detail"):
            self.assertIn(f'page === "{page}"', script)
        for status in (403, 404, 409, 429):
            self.assertIn(f'{status}: "', script)
        self.assertIn("loadAllPages", script)
        self.assertIn("setupPagedList", script)
        self.assertIn("/api/v1/leads/work-queue/", script)
        self.assertIn('`/customers/${lead.customer}/`', script)
        self.assertIn('`/interactions/?lead=${lead.id}`', script)
        self.assertIn('`/sales/?lead=${lead.id}`', script)
        self.assertIn('credentials: "same-origin"', script)
        for page in ("sales-documents", "sales-document-detail", "sales-document-report"):
            self.assertIn(f'page === "{page}"', script)
        self.assertIn("/api/v1/sales-documents/", script)
        self.assertIn("/api/v1/reports/sales-documents/", script)

    def test_forms_do_not_offer_server_managed_fields(self):
        customer_detail = (ROOT / "common" / "templates" / "common" / "customers" / "detail.html").read_text(encoding="utf-8")
        lead_detail = (ROOT / "common" / "templates" / "common" / "leads" / "detail.html").read_text(encoding="utf-8")
        interaction_list = (ROOT / "common" / "templates" / "common" / "interactions" / "list.html").read_text(encoding="utf-8")

        customer_form = customer_detail.split('id="edit-customer-form"', 1)[1].split("</form>", 1)[0]
        lead_form = lead_detail.split('id="edit-lead-form"', 1)[1].split("</form>", 1)[0]
        interaction_form = interaction_list.split('id="create-interaction-form"', 1)[1].split("</form>", 1)[0]
        for field in ("created_by", "is_active"):
            self.assertNotIn(f'name="{field}"', customer_form)
        # `status` is deliberately absent from this list: the person working the
        # campaign sets it, and the service validates it against the three
        # permitted states. Ownership and assignment stay server-managed.
        for field in ("customer", "assigned_to", "assigned_by", "assigned_at", "created_by", "source_payload"):
            self.assertNotIn(f'name="{field}"', lead_form)
        self.assertIn('name="status"', lead_form)
        for field in ("customer", "agent"):
            self.assertNotIn(f'name="{field}"', interaction_form)

    def test_customer_profile_has_new_fields_relations_and_deactivate_only(self):
        customer_list = (ROOT / "common" / "templates" / "common" / "customers" / "list.html").read_text(encoding="utf-8")
        customer_detail = (ROOT / "common" / "templates" / "common" / "customers" / "detail.html").read_text(encoding="utf-8")
        script = (ROOT / "common" / "static" / "common" / "forooshbin-app.js").read_text(encoding="utf-8")

        for field in ("postal_code", "category"):
            self.assertIn(f'name="{field}"', customer_list)
            self.assertIn(f'name="{field}"', customer_detail)
            self.assertIn(f'"{field}"', script)
        for relation in ("leads", "interactions"):
            self.assertIn(f'id="customer-{relation}-table-body"', customer_detail)
            self.assertIn(f'"{relation}", "{relation}"', script)
        # Related orders became related invoices: what is asked of a customer's
        # account is their invoices, and neither of the earlier panels survives.
        self.assertIn('id="customer-invoices-table-body"', customer_detail)
        self.assertNotIn('id="customer-orders-table-body"', customer_detail)
        self.assertNotIn('id="customer-sales-table-body"', customer_detail)
        # Both settlement columns are shown, because a manually settled invoice
        # reads as paid while its canonical balance is untouched.
        self.assertIn("<th>تسویه</th>", customer_detail)
        self.assertIn("<th>مانده</th>", customer_detail)

        # Two customer books, and the marketer is offered neither the switch nor
        # the kind selector. That hiding is not the authorisation — see
        # test_scope_attacks for what the backend refuses.
        self.assertIn('data-customer-kind="individual"', customer_list)
        self.assertIn('data-customer-kind="legal"', customer_list)
        self.assertIn('name="kind"', customer_list)
        self.assertEqual(customer_list.count("can_manage_customer_kinds"), 5)
        self.assertIn('id="open-export-customers"', customer_list)
        self.assertIn('id="open-import-customers"', customer_list)
        self.assertNotIn("دریافت XLSX", customer_list)

        # The destructive block is gone. Activation is a select at the top of
        # the page for a Platform Admin, and nothing anywhere deletes.
        self.assertNotIn('id="deactivate-customer"', customer_detail)
        self.assertNotIn('id="delete-customer"', customer_detail)
        self.assertIn('id="customer-active-select"', customer_detail)
        self.assertIn("can_change_activation", customer_detail)

    def test_active_terminology_keeps_customers_and_user_roles_distinct(self):
        customer_paths = (
            ROOT / "common" / "templates" / "common" / "customers" / "list.html",
            ROOT / "common" / "templates" / "common" / "customers" / "detail.html",
            ROOT / "common" / "templates" / "common" / "leads" / "list.html",
            ROOT / "common" / "templates" / "common" / "interactions" / "list.html",
            ROOT / "common" / "templates" / "common" / "interactions" / "detail.html",
            ROOT / "common" / "templates" / "common" / "sales" / "list.html",
            ROOT / "common" / "templates" / "common" / "sales" / "detail.html",
            # The performance page is now a toolbar plus this include, so the
            # wording it shows a user lives here.
            ROOT / "common" / "templates" / "common" / "includes" / "performance_panel.inc",
        )
        for path in customer_paths:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertIn("مشتری", text)
                self.assertNotIn("بازاریاب (کال سنتر)", text)
                self.assertNotRegex(text, r"مخاطب|مخاطبین")

        lead_detail = (ROOT / "common" / "templates" / "common" / "leads" / "detail.html").read_text(encoding="utf-8")
        # Wording, not markup: the label for each control must use the
        # approved term. Matching the whole tag would break on any restyle.
        # The lead form no longer names a single customer — a campaign is worked
        # from its target audience — so the customer control is gone from it.
        self.assertNotIn('for="lead-customer"', lead_detail)
        for control, term in (("reassign-to-user", "بازاریاب (کال سنتر)"),):
            label = re.search(rf'<label[^>]*for="{control}"[^>]*>([^<]*)</label>', lead_detail)
            self.assertIsNotNone(label, control)
            self.assertEqual(label.group(1).strip(), term)

        role_labels = {
            "sales_agent": "بازاریاب (کال سنتر)",
            "sales_manager": "مدیر فروشگاه",
            "company_it": "مدیر فنی مشتری",
            "platform_admin": "مدیر پلتفرم",
        }
        script = (ROOT / "common" / "static" / "common" / "forooshbin-app.js").read_text(encoding="utf-8")
        views = (ROOT / "common" / "ui_views.py").read_text(encoding="utf-8")
        user_detail = (ROOT / "common" / "templates" / "common" / "users" / "detail.html").read_text(encoding="utf-8")
        from accounts.access import ROLE_LABELS

        for role, label in role_labels.items():
            with self.subTest(role=role):
                self.assertIn(f'{role}: "{label}"', script)
                self.assertIn(label, views)
                # The role selector is rendered from `assignable_roles`, not
                # hardcoded in the template, so the label contract now lives
                # beside the rule that decides which roles are offered.
                self.assertEqual(ROLE_LABELS[role], label)
        # No *role* is hardcoded as an option any more. The workstream select
        # legitimately still lists its two fixed values inline.
        for role in role_labels:
            self.assertNotIn(f'<option value="{role}"', user_detail)
        self.assertIn("{% for value, label in assignable_roles %}", user_detail)
        self.assertIn('not_found_title = "مشتری پیدا نشد"', views)
        self.assertNotIn("مشخصات بازاریاب (کال سنتر) ذخیره شد", script)

        base = (ROOT / "common" / "templates" / "common" / "base.html").read_text(encoding="utf-8")
        # The customers entry is a theme menu item now, so its label sits in a
        # `menu-title` span rather than directly inside the anchor. What is
        # pinned here is the wording and the target, not the markup around them.
        customers_link = re.search(
            r'data-module="customers"[^>]*href="\{% url .common_ui:customers. %\}"[^>]*>(.*?)</a>',
            base,
            re.DOTALL,
        )
        self.assertIsNotNone(customers_link)
        self.assertIn("مشتریان", customers_link.group(1))
        branding = (ROOT / "scripts" / "check_html_branding.py").read_text(encoding="utf-8")
        self.assertIn('"contacts": "مشتریان"', branding)
        self.assertIn('"customers": "مشتریان"', branding)
        self.assertIn('"add-contact": "افزودن مشتری"', branding)
        self.assertIn('"edit-contact": "ویرایش مشتری"', branding)


class SalesShellScopeTests(TestCase):
    password = "Strong-pass-983!"

    def setUp(self):
        self.roles = {
            role: User.objects.create_user(username=f"shell-{role}", password=self.password, role=role)
            for role in User.Role.values
        }
        self.agent = self.roles[User.Role.SALES_AGENT]
        self.other_agent = User.objects.create_user(
            username="shell-other-agent",
            password=self.password,
            role=User.Role.SALES_AGENT,
        )
        self.manager = self.roles[User.Role.SALES_MANAGER]
        self.own_customer, self.own_lead, self.own_interaction = self._graph(
            self.agent, "مشتری مجاز", "09121112222"
        )
        self.hidden_customer, self.hidden_lead, self.hidden_interaction = self._graph(
            self.other_agent, "مشتری پنهان", "09123334444"
        )

    def _graph(self, actor, name, phone):
        customer = create_customer_with_phone(
            actor=actor,
            full_name=name,
            phone={"raw_phone": phone, "is_primary": True},
        )
        lead = create_lead(actor=actor, customer=customer, source="manual")
        assign_lead(actor=self.manager, lead=lead, to_user=actor, reason="manual assignment")
        interaction = record_interaction(
            actor=actor,
            lead=lead,
            phone=phone,
            direction=Interaction.Direction.OUTBOUND,
            outcome="ثبت دستی",
            occurred_at=timezone.now(),
        )
        return customer, lead, interaction

    def test_browser_direct_ids_apply_all_four_role_scopes(self):
        paths = (
            (f"/customers/{self.hidden_customer.pk}/", "مشتری پیدا نشد"),
            (f"/leads/{self.hidden_lead.pk}/", "سرنخ پیدا نشد"),
            (f"/interactions/{self.hidden_interaction.pk}/", "تماس پیدا نشد"),
        )
        for role, actor in self.roles.items():
            self.client.force_login(actor)
            for path, message in paths:
                with self.subTest(role=role, path=path):
                    response = self.client.get(path)
                    if role == User.Role.SALES_AGENT:
                        self.assertEqual(response.status_code, 404)
                        self.assertContains(response, message, status_code=404)
                    else:
                        self.assertEqual(response.status_code, 200)

    def test_api_direct_ids_apply_all_four_role_scopes(self):
        paths = (
            f"/api/v1/customers/{self.hidden_customer.pk}/",
            f"/api/v1/customers/{self.hidden_customer.pk}/leads/",
            f"/api/v1/customers/{self.hidden_customer.pk}/interactions/",
            f"/api/v1/customers/{self.hidden_customer.pk}/sales/",
            f"/api/v1/customer-phones/{self.hidden_customer.phones.get().pk}/",
            f"/api/v1/leads/{self.hidden_lead.pk}/",
            f"/api/v1/interactions/{self.hidden_interaction.pk}/",
            f"/api/v1/leads/{self.hidden_lead.pk}/assignment-history/",
        )
        client = APIClient()
        for role, actor in self.roles.items():
            client.force_authenticate(actor)
            for path in paths:
                with self.subTest(role=role, path=path):
                    expected = 404 if role == User.Role.SALES_AGENT else 200
                    self.assertEqual(client.get(path).status_code, expected)

    def test_agent_custom_actions_hide_out_of_scope_ids(self):
        client = APIClient()
        client.force_authenticate(self.agent)
        hidden_phone = self.hidden_customer.phones.get()
        phone_response = client.post(f"/api/v1/customer-phones/{hidden_phone.pk}/deactivate/")
        lead_response = client.post(
            f"/api/v1/leads/{self.hidden_lead.pk}/reassign/",
            {"to_user": self.agent.pk},
            format="json",
        )
        self.assertEqual(phone_response.status_code, 404)
        self.assertEqual(lead_response.status_code, 404)
        hidden_phone.refresh_from_db()
        self.hidden_lead.refresh_from_db()
        self.assertTrue(hidden_phone.is_active)
        self.assertEqual(self.hidden_lead.assigned_to, self.other_agent)

    def test_all_roles_see_real_core_navigation(self):
        for role, actor in self.roles.items():
            self.client.force_login(actor)
            response = self.client.get("/customers/")
            with self.subTest(role=role):
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'href="/customers/"')
                self.assertContains(response, 'href="/leads/"')
                self.assertContains(response, 'href="/interactions/"')
                if role == User.Role.SALES_AGENT:
                    self.assertNotContains(response, "مدیریت کاربران")

    def test_reassignment_controls_match_role_scope(self):
        for role, actor in self.roles.items():
            self.client.force_login(actor)
            response = self.client.get(f"/leads/{self.own_lead.pk}/")
            with self.subTest(role=role):
                if role == User.Role.SALES_AGENT:
                    self.assertNotContains(response, 'id="reassign-lead-form"')
                else:
                    self.assertContains(response, 'id="reassign-lead-form"')

    def test_unassigned_agent_lead_is_view_only_but_elevated_role_can_edit(self):
        unassigned = create_lead(actor=self.agent, customer=self.own_customer, source="unassigned")
        self.client.force_login(self.agent)
        agent_response = self.client.get(f"/leads/{unassigned.pk}/")
        agent_form = agent_response.content.decode("utf-8").split('id="edit-lead-form"', 1)[1].split("</form>", 1)[0]
        self.assertIn("<fieldset disabled>", agent_form)
        self.assertNotIn('type="submit"', agent_form)

        self.client.force_login(self.manager)
        manager_form = self.client.get(f"/leads/{unassigned.pk}/").content.decode("utf-8").split('id="edit-lead-form"', 1)[1].split("</form>", 1)[0]
        self.assertIn("<fieldset>", manager_form)
        self.assertIn('type="submit"', manager_form)


class SalesShellApiTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="shell-api-manager",
            password="Strong-pass-983!",
            role=User.Role.SALES_MANAGER,
        )
        self.agent = User.objects.create_user(
            username="shell-api-agent",
            password="Strong-pass-983!",
            role=User.Role.SALES_AGENT,
        )
        self.customer = create_customer_with_phone(
            actor=self.agent,
            full_name="مشتری تست رابط",
            phone={"raw_phone": "09125556666", "is_primary": True},
        )
        self.lead = create_lead(actor=self.agent, customer=self.customer)
        assign_lead(actor=self.manager, lead=self.lead, to_user=self.agent, reason="first")
        self.client = APIClient()

    def test_phone_filter_edit_deactivate_and_conflict_contract(self):
        self.client.force_authenticate(self.agent)
        created = self.client.post(
            "/api/v1/customer-phones/",
            {"customer": self.customer.pk, "raw_phone": "۰۹۱۲ ۷۷۷ ۸۸۸۸", "label": "همراه"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        phone_id = created.data["id"]
        self.assertEqual(created.data["normalized_phone"], "+989127778888")

        filtered = self.client.get(f"/api/v1/customer-phones/?customer={self.customer.pk}&ordering=-is_primary")
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual({row["customer"] for row in filtered.data["results"]}, {self.customer.pk})
        rejected = self.client.patch(
            f"/api/v1/customer-phones/{phone_id}/", {"is_active": False}, format="json"
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("is_active", rejected.data)

        deactivated = self.client.post(f"/api/v1/customer-phones/{phone_id}/deactivate/")
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.data["is_active"])
        self.assertFalse(deactivated.data["is_primary"])
        self.assertEqual(
            ActivityLog.objects.filter(
                operation="customer_phone.deactivated", object_id=str(phone_id)
            ).count(),
            1,
        )
        repeated = self.client.post(f"/api/v1/customer-phones/{phone_id}/deactivate/")
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(repeated.data["error"]["code"], "conflict")

    def test_assignment_history_and_dedicated_assignee_options(self):
        self.client.force_authenticate(self.agent)
        own_history = self.client.get(f"/api/v1/leads/{self.lead.pk}/assignment-history/?page=1")
        self.assertEqual(own_history.status_code, 200)
        self.assertEqual(own_history.data["count"], 1)
        self.assertEqual(own_history.data["results"][0]["to_user"], self.agent.pk)
        self.assertEqual(self.client.get("/api/v1/leads/assignees/?page=1").status_code, 403)

        self.client.force_authenticate(self.manager)
        assignees = self.client.get("/api/v1/leads/assignees/?page=1")
        self.assertEqual(assignees.status_code, 200)
        self.assertIn(self.agent.pk, {row["id"] for row in assignees.data["results"]})
        self.assertEqual(set(assignees.data["results"][0]), {"id", "username", "first_name", "last_name"})

    @mock.patch.object(SensitiveRateThrottle, "get_rate", lambda self: "1/min")
    def test_phone_deactivation_has_real_throttle_state(self):
        cache.clear()
        self.client.force_authenticate(self.agent)
        phone = self.customer.phones.get()
        first = self.client.post(f"/api/v1/customer-phones/{phone.pk}/deactivate/")
        second = self.client.post(f"/api/v1/customer-phones/{phone.pk}/deactivate/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.data["error"]["code"], "throttled")

    def test_customer_search_sort_and_pagination_are_real(self):
        for index in range(25):
            create_customer_with_phone(actor=self.agent, full_name=f"مشتری تست {index:02d}")
        self.client.force_authenticate(self.manager)
        page = self.client.get("/api/v1/customers/?search=مشتری&ordering=full_name&page=1")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.data["count"], 26)
        self.assertIsNotNone(page.data["next"])
        self.assertEqual(len(page.data["results"]), 25)
        second_page = self.client.get("/api/v1/customers/?search=مشتری&ordering=full_name&page=2")
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(len(second_page.data["results"]), 1)
        names = [row["full_name"] for row in page.data["results"] + second_page.data["results"]]
        self.assertEqual(names, sorted(names))
        self.assertIn("مشتری تست رابط", names)

    def test_server_managed_customer_agent_and_ownership_fields_are_rejected(self):
        self.client.force_authenticate(self.agent)
        attempts = (
            ("post", "/api/v1/customers/", {"full_name": "بد", "created_by_display": "fake"}, "created_by_display"),
            ("patch", f"/api/v1/leads/{self.lead.pk}/", {"assigned_to_display": "fake"}, "assigned_to_display"),
            ("post", "/api/v1/interactions/", {
                "lead": self.lead.pk,
                "phone": "09125556666",
                "direction": "outbound",
                "outcome": "ثبت",
                "occurred_at": timezone.now().isoformat(),
                "agent_display": "fake",
            }, "agent_display"),
        )
        for method, path, payload, field in attempts:
            with self.subTest(path=path, field=field):
                response = getattr(self.client, method)(path, payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)


class SalesDocumentFormMarkupTests(TestCase):
    """The postal-transition form must parse into the elements the JS expects.

    A single unclosed attribute quote previously swallowed the `reason` field's
    error paragraph into the input tag, so `showError()` targeted an `<input>`
    and the message never rendered. These assertions run against the parsed DOM
    of the real rendered page rather than the template source.
    """

    def setUp(self):
        self.manager = User.objects.create_user(
            username="doc.markup.manager",
            password="Long-Safe-Pass-741!",
            role=User.Role.SALES_MANAGER,
        )
        customer = create_customer_with_phone(actor=self.manager, full_name="مشتری سند")
        self.document = register_sales_document(
            actor=self.manager,
            customer=customer,
            document_number="MARKUP-DOC-1",
            postal_status="ثبت شد",
        )
        self.client.force_login(self.manager)

    def _parsed_page(self):
        response = self.client.get(f"/sales-documents/{self.document.pk}/")
        self.assertEqual(response.status_code, 200)

        collected = []

        class Collector(HTMLParser):
            def handle_starttag(self, tag, attrs):
                collected.append((tag, dict(attrs)))

        Collector().feed(response.content.decode("utf-8"))
        return collected

    def _element(self, elements, tag, **match):
        found = [
            attrs
            for element_tag, attrs in elements
            if element_tag == tag and all(attrs.get(key) == value for key, value in match.items())
        ]
        return found

    def test_reason_field_keeps_a_well_formed_length_limit(self):
        elements = self._parsed_page()
        reason = self._element(elements, "input", id="postal-reason")
        self.assertEqual(len(reason), 1)
        # The malformed markup emitted maxlength="500><p class=". Chrome's
        # non-negative-integer parsing still yielded 500, so the limit itself
        # survived in practice; this asserts the attribute is well formed rather
        # than relying on that lenient parsing.
        self.assertEqual(reason[0].get("maxlength"), "500")
        self.assertEqual(reason[0].get("name"), "reason")

    def test_reason_field_error_paragraph_is_a_separate_element(self):
        elements = self._parsed_page()
        paragraphs = self._element(elements, "p", **{"data-error-for": "reason"})
        self.assertEqual(len(paragraphs), 1)
        # What matters is that it is a separate <p> carrying the hook
        # showError() writes into; the visual class comes from the theme.
        self.assertIn("text-danger", paragraphs[0].get("class", ""))

    def test_reason_input_carries_no_swallowed_attributes(self):
        elements = self._parsed_page()
        reason = self._element(elements, "input", id="postal-reason")[0]
        # showError() targets [data-error-for]; if that attribute lands on the
        # input itself, the message is written to an element that renders none.
        self.assertNotIn("data-error-for", reason)
        # Only the expected attributes, plus the theme's styling class.
        self.assertEqual(set(reason) - {"class"}, {"id", "name", "maxlength"})

    def test_every_transition_form_field_has_its_own_error_target(self):
        elements = self._parsed_page()
        for field in ("to_status", "reason"):
            with self.subTest(field=field):
                self.assertEqual(
                    len(self._element(elements, "p", **{"data-error-for": field})), 1
                )
                self.assertEqual(
                    len(self._element(elements, "input", name=field)), 1
                )
