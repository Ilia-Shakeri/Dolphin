from django.conf import settings
from django.contrib.auth import SESSION_KEY, logout
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView

from accounts.access import (
    assignable_roles,
    capabilities_for,
    crm_identities,
    has_any_capability,
    is_crm_identity,
)
from accounts.models import User
from common.deployment.profile import active_profile, feature_enabled
from common.pdf import (
    PdfRendererBusy,
    PdfRendererUnavailable,
    inline_stylesheet,
    render_html_to_pdf,
    renderer_is_available,
)
from common.permissions import FeatureGatedViewMixin
from auditlog.selectors import activity_logs_for
from aftersales.selectors import after_sales_requests_for
from billing.money import printed_line_breakdown
from billing.words import amount_in_words
from billing.selectors import (
    cheques_for,
    installment_plans_for,
    invoices_for,
    orders_for,
    payments_for,
)
from inventory.selectors import stock_items_for, stock_movements_for, warehouses_for
from reports.selectors import users_for_performance_report
from sales.selectors import (
    customers_for,
    interactions_for,
    leads_for,
    product_categories_for,
    products_for,
    sales_documents_for,
    sales_for,
)


# Persian labels for backend-owned status vocabularies. The backend value stays
# the single source of truth; these are presentation only and a value with no
# entry falls back to the raw code rather than being hidden.
DOCUMENT_STATUS_LABELS = {
    "draft": "پیش‌نویس",
    "sent": "ارسال‌شده",
    "accepted": "پذیرفته‌شده",
    "rejected": "ردشده",
    "expired": "منقضی‌شده",
    "cancelled": "لغوشده",
    "confirmed": "تأییدشده",
    "fulfilled": "تحویل‌شده",
    "issued": "صادرشده",
}
SETTLEMENT_LABELS = {
    "unpaid": "تسویه‌نشده",
    "partially_paid": "تسویه جزئی",
    "paid": "تسویه کامل",
}

#: How each dashboard tile is presented: a keenicon from the theme's own set and
#: a Metronic accent. Purely visual — the figure and its scope come from the
#: capability check above, never from this table.
DEFAULT_WIDGET_STYLE = {"icon": "ki-element-11", "accent": "primary", "icon_paths": 4}
WIDGET_STYLE = {
    "customers": {"icon": "ki-profile-user", "accent": "primary", "icon_paths": 4},
    "leads": {"icon": "ki-phone", "accent": "info", "icon_paths": 2},
    "interactions": {"icon": "ki-message-text-2", "accent": "info", "icon_paths": 3},
    "sales": {"icon": "ki-handcart", "accent": "success", "icon_paths": 1},
    "sales_documents": {"icon": "ki-delivery", "accent": "warning", "icon_paths": 5},
    "after_sales": {"icon": "ki-shield-tick", "accent": "warning", "icon_paths": 2},
    "users": {"icon": "ki-people", "accent": "dark", "icon_paths": 5},
    "audit": {"icon": "ki-shield-search", "accent": "dark", "icon_paths": 4},
}

ROLE_LABELS = {
    User.Role.SALES_AGENT: "بازاریاب (کال سنتر)",
    User.Role.SALES_MANAGER: "مدیر فروشگاه",
    User.Role.COMPANY_IT: "مدیر فنی مشتری",
    User.Role.PLATFORM_ADMIN: "مدیر پلتفرم",
}


@method_decorator(ensure_csrf_cookie, name="dispatch")
class DolphinLoginView(TemplateView):
    template_name = "common/login.html"

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user):
            return redirect("common_ui:home")
        if request.user.is_authenticated or SESSION_KEY in request.session:
            logout(request)
        return super().dispatch(request, *args, **kwargs)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class ActiveCrmView(FeatureGatedViewMixin, TemplateView):
    def dispatch(self, request, *args, **kwargs):
        if not is_crm_identity(request.user):
            if request.user.is_authenticated or SESSION_KEY in request.session:
                logout(request)
            return redirect("common_ui:login")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        capabilities = capabilities_for(self.request.user)
        # Feature availability is a separate control from role permission: the
        # template hides a link when either says no, and the backend refuses
        # regardless of what the template rendered.
        context["features"] = active_profile().features
        context["capabilities"] = capabilities
        context["role_label"] = ROLE_LABELS[self.request.user.role]
        if self.request.user.role == User.Role.SALES_AGENT and self.request.user.workstream == User.Workstream.AFTER_SALES:
            context["role_label"] = f'{context["role_label"]} — خدمات پس از فروش'
        context["can_manage_users"] = has_any_capability(
            self.request.user,
            "users.manage_agents",
            "users.manage_non_platform",
            "users.manage_all",
        )
        context["can_change_roles"] = has_any_capability(
            self.request.user,
            "users.manage_non_platform",
            "users.manage_all",
        )
        context["user_admin_label"] = (
            "مدیریت بازاریابان" if "users.manage_agents" in capabilities else "مدیریت کاربران"
        )
        context["can_deactivate_customers"] = self.request.user.role in {
            User.Role.SALES_MANAGER,
            User.Role.COMPANY_IT,
            User.Role.PLATFORM_ADMIN,
        }
        # Mirrors `sales.services.STATUS_ADMINISTRATORS`. Client-1 gives the
        # store manager the same functional access as the platform admin; what
        # stays Platform-Admin-only is the security plane — user accounts,
        # sessions, the deployment — not business workflow.
        status_admin = self.request.user.role in {
            User.Role.SALES_MANAGER, User.Role.PLATFORM_ADMIN
        }
        context["can_change_activation"] = status_admin
        # An order's status decides whether goods leave the warehouse, so it is
        # held by the same roles. Everything else on the order stays editable by
        # whoever may work it.
        context["can_change_order_status"] = status_admin
        # Mirrors exactly what `_require_target_audience_editor` allows, so the
        # page never offers a control the service would refuse, nor hides one it
        # would accept.
        context["can_edit_target_audience"] = self.request.user.role != User.Role.SALES_AGENT
        # Two customer books. A marketer works the individual one and is not
        # offered the choice — mirroring `customers_for`, which confines their
        # scope to it in the database, and `_validate_customer_kind`, which
        # refuses them a legal customer on the way in.
        context["can_manage_customer_kinds"] = self.request.user.role != User.Role.SALES_AGENT
        context["can_reassign_leads"] = context["can_deactivate_customers"]
        context["can_manage_products"] = context["can_deactivate_customers"]
        context["can_cancel_sales"] = context["can_deactivate_customers"]
        context["can_manage_sales_documents"] = context["can_deactivate_customers"]
        context["can_manage_after_sales"] = "after_sales.manage" in capabilities
        context["can_view_company_reports"] = "reports.company" in capabilities
        context["can_manage_inventory"] = "inventory.manage" in capabilities
        context["can_read_inventory"] = bool(
            {"inventory.read", "inventory.manage"}.intersection(capabilities)
        )
        # Money capabilities. An agent prepares documents but never issues an
        # invoice, takes a payment, or reads the company ledger.
        context["can_manage_billing"] = bool(
            {"invoices.company", "orders.company"}.intersection(capabilities)
        )
        context["can_handle_payments"] = "payments.company" in capabilities
        context["can_view_ledger"] = bool(
            capabilities.intersection({"ledger.company", "ledger.own"})
        )
        context["can_view_sms_report"] = "sms.company" in capabilities
        # Same capability as the inbound report, and the same reasoning as
        # `send_outbound_sms` (communications/services.py): sending is a
        # manager-and-up capability for now, not yet opened to sales_agent.
        context["can_send_sms"] = "sms.company" in capabilities
        # Attachments: upload capability mirrors exactly the capability each
        # domain's own service layer already requires to write that parent
        # record (attachments/selectors.py's PARENT_WRITE_CAPABILITY) — shown
        # opportunistically per detail page; the API enforces it regardless.
        context["can_upload_attachment"] = {
            "customer": "customers.manage" in capabilities,
            "lead": "leads.manage" in capabilities,
            "invoice": "invoices.manage" in capabilities,
            "sales_document": "sales_documents.manage" in capabilities,
            "after_sales_request": bool({"after_sales.manage", "after_sales.work"}.intersection(capabilities)),
        }
        # Deletion is elevated-role-only regardless of parent type (product-
        # owner decision, 2026-09-03) — attachments/services.py's
        # ELEVATED_OPERATORS, checked here by role since it is not a
        # capability of its own.
        context["can_delete_attachments"] = is_crm_identity(self.request.user) and self.request.user.role in {
            "sales_manager", "company_it", "platform_admin",
        }
        # The same pair `DolphinUserProfileView` and the user-performance report
        # itself require — an after-sales agent holds neither, so they get no
        # "عملکرد من" entry pointing at a page that would just refuse them.
        context["can_view_own_profile"] = bool(
            {"reports.own", "reports.company"}.intersection(capabilities)
        )
        context["can_view_audit"] = feature_enabled("audit_log") and bool(
            {"audit.non_platform", "audit.all"}.intersection(capabilities)
        )
        context["is_platform_navigation"] = "dashboard.platform" in capabilities
        # 2026-09-02: real, irreversible row deletion — single or bulk, on
        # every list page — for a Platform Admin only, to correct a mistaken
        # entry. Everyone else still deactivates, same as before. Set once
        # here rather than per list view since every list page shares this
        # one root; the backend gate in `common.viewsets.HardDeleteMixin` is
        # what actually decides, regardless of what this hides or shows.
        context["can_hard_delete"] = self.request.user.role == User.Role.PLATFORM_ADMIN
        return context


class DolphinHomeView(ActiveCrmView):
    template_name = "common/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        capabilities = context["capabilities"]
        role = self.request.user.role
        dashboard = {
            User.Role.PLATFORM_ADMIN: ("پنل مدیر پلتفرم", "مدیریت سامانه، کاربران، رویدادها و همه بخش‌های عملیاتی"),
            User.Role.SALES_MANAGER: ("پنل مدیر فروشگاه", "نمای سراسری کسب‌وکار، عملیات فروش و گزارش‌های این استقرار"),
            User.Role.SALES_AGENT: ("میز کار بازاریاب", "سرنخ‌های تخصیص‌یافته، تماس‌های دستی و عملکرد خود شما"),
            User.Role.COMPANY_IT: ("پنل مدیر فنی مشتری", "دسترسی عملیاتی شرکت و مشاهده رویدادهای غیرپلتفرمی"),
        }[role]
        if role == User.Role.SALES_AGENT and self.request.user.workstream == User.Workstream.AFTER_SALES:
            dashboard = (
                "میز کار خدمات پس از فروش",
                "پرونده‌های تخصیص‌یافته و اقدام‌های ثبت‌شده شما",
            )
        widgets = []
        # A dashboard tile links into a module, so it needs the feature as well
        # as the capability. Both controls are consulted, neither replaces the
        # other, and the target page enforces both again.
        widget_features = {
            "customers": "customers",
            "leads": "leads",
            "interactions": "leads",
            "sales": "sales",
            "sales_documents": "sales_documents",
            "after_sales": "after_sales",
        }

        def add(capability, label, value, url_name):
            feature = widget_features[capability.split(".", 1)[0]]
            if capability in capabilities and feature_enabled(feature):
                module = capability.split(".", 1)[0]
                widgets.append({
                    "capability": capability,
                    "label": label,
                    "value": value,
                    "url_name": url_name,
                    # Presentation only. Keeping the icon and accent beside the
                    # figure means the card reads as a KPI rather than as a
                    # number on a blank tile, and the template stays free of a
                    # long `{% if %}` ladder over capability names.
                    **WIDGET_STYLE.get(module, DEFAULT_WIDGET_STYLE),
                })

        customer_scope = customers_for(self.request.user)
        lead_scope = leads_for(self.request.user)
        interaction_scope = interactions_for(self.request.user)
        sale_scope = sales_for(self.request.user)
        document_scope = sales_documents_for(self.request.user)
        after_sales_scope = after_sales_requests_for(self.request.user)
        add("customers.scoped", "مشتریان مجاز", customer_scope.count(), "common_ui:customers")
        add("customers.company", "مشتریان شرکت", customer_scope.count(), "common_ui:customers")
        add("leads.scoped", "صف سرنخ من", lead_scope.count(), "common_ui:leads")
        add("leads.company", "سرنخ‌های شرکت", lead_scope.count(), "common_ui:leads")
        add("interactions.scoped", "تماس‌های مجاز من", interaction_scope.count(), "common_ui:interactions")
        add("interactions.company", "فعالیت مرکز تماس", interaction_scope.count(), "common_ui:interactions")
        add("sales.own", "فروش‌های من", sale_scope.count(), "common_ui:sales")
        add("sales.company", "فروش‌های شرکت", sale_scope.count(), "common_ui:sales")
        add("sales_documents.scoped", "اسناد فروش مجاز", document_scope.count(), "common_ui:sales-documents")
        add("sales_documents.company", "اسناد فروش داخلی", document_scope.count(), "common_ui:sales-documents")
        add("after_sales.assigned", "پرونده‌های خدمات من", after_sales_scope.count(), "common_ui:after-sales")
        add("after_sales.company", "پرونده‌های خدمات پس از فروش", after_sales_scope.count(), "common_ui:after-sales")
        if context["can_manage_users"]:
            user_scope = crm_identities(User.objects.all())
            if role == User.Role.SALES_MANAGER:
                user_scope = user_scope.filter(role=User.Role.SALES_AGENT)
            elif role == User.Role.COMPANY_IT:
                user_scope = user_scope.exclude(role=User.Role.PLATFORM_ADMIN)
            widgets.append({
                "capability": next(item for item in capabilities if item.startswith("users.manage_")),
                "label": context["user_admin_label"],
                "value": user_scope.count(),
                "url_name": "common_ui:users",
                **WIDGET_STYLE["users"],
            })
        if context["can_view_audit"]:
            widgets.append({
                "capability": "audit.all" if "audit.all" in capabilities else "audit.non_platform",
                "label": "رویدادهای قابل مشاهده",
                "value": activity_logs_for(self.request.user).count(),
                "url_name": "common_ui:activity-logs",
                **WIDGET_STYLE["audit"],
            })
        context["dashboard_title"], context["dashboard_summary"] = dashboard
        context["dashboard_capability"] = next(item for item in capabilities if item.startswith("dashboard."))
        context["dashboard_widgets"] = widgets
        return context


class UserAdminView(ActiveCrmView):
    def dispatch(self, request, *args, **kwargs):
        if not is_crm_identity(request.user):
            if request.user.is_authenticated or SESSION_KEY in request.session:
                logout(request)
            return redirect("common_ui:login")
        if not has_any_capability(
            request.user,
            "users.manage_agents",
            "users.manage_non_platform",
            "users.manage_all",
        ):
            return self.render_to_response(
                self.get_context_data(
                    error_status=403,
                    error_title="دسترسی مجاز نیست",
                    error_message="شما اجازه مدیریت کاربران را ندارید.",
                ),
                status=403,
            )
        return super().dispatch(request, *args, **kwargs)


class DolphinUserListView(UserAdminView):
    template_name = "common/users/list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Create User offers exactly the roles `change-role` would also
        # accept from this same admin — one list, so the two screens can
        # never disagree about what is on offer.
        context["assignable_roles"] = assignable_roles(self.request.user)
        return context


class DolphinUserDetailView(UserAdminView):
    template_name = "common/users/detail.html"

    def get(self, request, *args, **kwargs):
        queryset = crm_identities(User.objects.all())
        if request.user.role == User.Role.SALES_MANAGER:
            queryset = queryset.filter(role=User.Role.SALES_AGENT)
        elif request.user.role == User.Role.COMPANY_IT:
            queryset = queryset.exclude(role=User.Role.PLATFORM_ADMIN)
        if not queryset.filter(pk=kwargs["user_id"]).exists():
            return self.render_to_response(
                self.get_context_data(
                    error_status=404,
                    error_title="کاربر پیدا نشد",
                    error_message="کاربر در محدوده دسترسی شما وجود ندارد.",
                ),
                status=404,
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["target_user_id"] = self.kwargs["user_id"]
        context["assignable_roles"] = assignable_roles(self.request.user)
        return context


def _profile_initials(user):
    """One or two letters for the avatar circle — there is no photo upload."""
    name = (user.get_full_name() or user.username).strip()
    parts = [part for part in name.split() if part]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return name[:2].upper() if name else "?"


class DolphinUserProfileView(ActiveCrmView):
    """One seller's own page: identity, and the performance report scoped to them alone.

    Gated on `reports.own`/`reports.company` — the same pair the company
    performance report requires — rather than on `users.manage_*`, which only
    Platform Admin ever holds (see `accounts.access.ROLE_CAPABILITIES`). A
    Sales Manager already sees every seller's rows on that company report; this
    is the same data, addressed one seller at a time, so it asks the same
    permission rather than the user-administration one `DolphinUserDetailView`
    and `/users/` themselves require.

    `users_for_performance_report(request.user)` is the actual scope boundary:
    for a Sales Agent it is themselves alone, so this page is their own and
    nobody else's; for an elevated role it is every crm identity, so any
    seller's page opens. The reports API re-derives the identical scope on
    every request this page makes, so nothing here is the authorization by
    itself — only what decides whether the shell renders at all.
    """

    required_feature = "reports"
    template_name = "common/users/profile.html"

    def dispatch(self, request, *args, **kwargs):
        if not is_crm_identity(request.user):
            if request.user.is_authenticated or SESSION_KEY in request.session:
                logout(request)
            return redirect("common_ui:login")
        if not has_any_capability(request.user, "reports.own", "reports.company"):
            return self.render_to_response(
                self.get_context_data(
                    error_status=403,
                    error_title="دسترسی مجاز نیست",
                    error_message="شما اجازه مشاهده این پروفایل را ندارید.",
                ),
                status=403,
            )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        target = users_for_performance_report(request.user).filter(pk=kwargs["user_id"]).first()
        if target is None:
            return self.render_to_response(
                self.get_context_data(
                    error_status=404,
                    error_title="پروفایل پیدا نشد",
                    error_message="این پروفایل در محدوده دسترسی شما وجود ندارد.",
                ),
                status=404,
            )
        self._target = target
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        target = getattr(self, "_target", None)
        if target is None:
            return context
        context["target_user_id"] = target.pk
        context["target_username"] = target.username
        context["target_display_name"] = target.get_full_name() or target.username
        context["target_role_label"] = ROLE_LABELS.get(target.role, target.role)
        context["target_phone"] = target.phone
        context["target_email"] = target.email
        context["target_is_active"] = target.is_active
        context["target_initials"] = _profile_initials(target)
        context["is_own_profile"] = target.pk == self.request.user.pk
        return context


class DolphinMyProfileView(ActiveCrmView):
    """`/profile/` — "my own profile", with no id to look up first.

    A redirect rather than a second template, so there is exactly one profile
    page and one place its permission and rendering logic can drift.
    """

    required_feature = "reports"

    def get(self, request, *args, **kwargs):
        return redirect("common_ui:user-profile", user_id=request.user.pk)


class DolphinCustomerListView(ActiveCrmView):
    required_feature = "customers"
    template_name = "common/customers/list.html"


class ScopedDetailView(ActiveCrmView):
    object_id_kwarg = "object_id"
    context_id_name = "object_id"
    not_found_title = "مورد پیدا نشد"
    not_found_message = "این مورد در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        raise NotImplementedError

    def get(self, request, *args, **kwargs):
        object_id = kwargs[self.object_id_kwarg]
        if not self.scoped_queryset().filter(pk=object_id).exists():
            return self.render_to_response(
                self.get_context_data(
                    error_status=404,
                    error_title=self.not_found_title,
                    error_message=self.not_found_message,
                ),
                status=404,
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[self.context_id_name] = self.kwargs[self.object_id_kwarg]
        return context


class DolphinCustomerDetailView(ScopedDetailView):
    required_feature = "customers"
    template_name = "common/customers/detail.html"
    object_id_kwarg = "customer_id"
    context_id_name = "customer_id"
    not_found_title = "مشتری پیدا نشد"
    not_found_message = "مشتری در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return customers_for(self.request.user)


class DolphinLeadListView(ActiveCrmView):
    required_feature = "leads"
    template_name = "common/leads/list.html"


class DolphinLeadCalendarView(ActiveCrmView):
    """The same leads, drawn on a month grid by `next_follow_up_at`.

    No extra permission check beyond the feature gate: exactly like
    `DolphinLeadListView`, the page renders for anyone whose deployment runs
    `leads`, and `leads_for`/`leads.scoped`/`leads.company` on the API behind
    it are what actually decide whose leads it can ever draw. A viewer with
    neither capability opens an empty calendar, the same way they would see
    an empty list on the ordinary leads page.
    """

    required_feature = "leads"
    template_name = "common/leads/calendar.html"


class DolphinLeadDetailView(ScopedDetailView):
    required_feature = "leads"
    template_name = "common/leads/detail.html"
    object_id_kwarg = "lead_id"
    context_id_name = "lead_id"
    not_found_title = "سرنخ پیدا نشد"
    not_found_message = "سرنخ در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return leads_for(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lead = self.scoped_queryset().filter(pk=self.kwargs["lead_id"]).only("assigned_to_id").first()
        context["can_edit_lead"] = bool(
            lead
            and (
                self.request.user.role in {
                    User.Role.SALES_MANAGER,
                    User.Role.COMPANY_IT,
                    User.Role.PLATFORM_ADMIN,
                }
                or lead.assigned_to_id == self.request.user.pk
            )
        )
        return context


class DolphinInteractionListView(ActiveCrmView):
    required_feature = "leads"
    template_name = "common/interactions/list.html"


class DolphinInteractionDetailView(ScopedDetailView):
    required_feature = "leads"
    template_name = "common/interactions/detail.html"
    object_id_kwarg = "interaction_id"
    context_id_name = "interaction_id"
    not_found_title = "تماس پیدا نشد"
    not_found_message = "تماس در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return interactions_for(self.request.user)


class DolphinProductListView(ActiveCrmView):
    required_feature = "products"
    template_name = "common/products/list.html"


class DolphinProductCategoryListView(ActiveCrmView):
    required_feature = "products"
    template_name = "common/product_categories/list.html"


class DolphinProductCategoryDetailView(ScopedDetailView):
    required_feature = "products"
    template_name = "common/product_categories/detail.html"
    object_id_kwarg = "category_id"
    context_id_name = "category_id"
    not_found_title = "دسته‌بندی پیدا نشد"
    not_found_message = "دسته‌بندی در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return product_categories_for(self.request.user)


class DolphinProductDetailView(ScopedDetailView):
    required_feature = "products"
    template_name = "common/products/detail.html"
    object_id_kwarg = "product_id"
    context_id_name = "product_id"

    def scoped_queryset(self):
        return products_for(self.request.user)


class DolphinSaleListView(ActiveCrmView):
    required_feature = "sales"
    template_name = "common/sales/list.html"


class DolphinSaleDetailView(ScopedDetailView):
    required_feature = "sales"
    template_name = "common/sales/detail.html"
    object_id_kwarg = "sale_id"
    context_id_name = "sale_id"

    def scoped_queryset(self):
        return sales_for(self.request.user)


class DolphinSalesDocumentListView(ActiveCrmView):
    required_feature = "sales_documents"
    template_name = "common/sales_documents/list.html"


class DolphinSalesDocumentDetailView(ScopedDetailView):
    required_feature = "sales_documents"
    template_name = "common/sales_documents/detail.html"
    object_id_kwarg = "document_id"
    context_id_name = "document_id"
    not_found_title = "سند فروش پیدا نشد"
    not_found_message = "سند فروش در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return sales_documents_for(self.request.user)


class DolphinUserPerformanceView(ActiveCrmView):
    required_feature = "reports"
    template_name = "common/reports/user_performance.html"

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(request.user, "reports.own", "reports.company"):
            return self.render_to_response(self.get_context_data(
                error_status=403, error_title="دسترسی مجاز نیست",
                error_message="شما اجازه مشاهده این گزارش را ندارید.",
            ), status=403)
        return super().dispatch(request, *args, **kwargs)


class DolphinSalesDocumentReportView(ActiveCrmView):
    required_feature = "sales_documents"
    template_name = "common/reports/sales_documents.html"

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(request.user, "reports.own", "reports.company"):
            return self.render_to_response(self.get_context_data(
                error_status=403, error_title="دسترسی مجاز نیست",
                error_message="شما اجازه مشاهده این گزارش را ندارید.",
            ), status=403)
        return super().dispatch(request, *args, **kwargs)


class DolphinInboundSMSReportView(ActiveCrmView):
    required_feature = "inbound_sms"
    template_name = "common/reports/inbound_sms.html"

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(request.user, "sms.company"):
            return self.render_to_response(self.get_context_data(
                error_status=403, error_title="دسترسی مجاز نیست",
                error_message="شما اجازه مشاهده گزارش پیامک ورودی را ندارید.",
            ), status=403)
        return super().dispatch(request, *args, **kwargs)


class DolphinOutboundSMSView(ActiveCrmView):
    required_feature = "outbound_sms"
    template_name = "common/sms/outbound.html"

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(request.user, "sms.company"):
            return self.render_to_response(self.get_context_data(
                error_status=403, error_title="دسترسی مجاز نیست",
                error_message="شما اجازه ارسال یا مشاهده پیامک را ندارید.",
            ), status=403)
        return super().dispatch(request, *args, **kwargs)


class AfterSalesAccessView(ActiveCrmView):
    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(
            request.user, "after_sales.assigned", "after_sales.company"
        ):
            return self.render_to_response(self.get_context_data(
                error_status=403, error_title="دسترسی مجاز نیست",
                error_message="شما اجازه مشاهده خدمات پس از فروش را ندارید.",
            ), status=403)
        return super().dispatch(request, *args, **kwargs)


class DolphinAfterSalesCalendarView(AfterSalesAccessView):
    """The same after-sales cases, drawn on a month grid by
    `next_appointment_at` — the after-sales mirror of `DolphinLeadCalendarView`.
    """

    required_feature = "after_sales"
    template_name = "common/after_sales/calendar.html"


class DolphinAfterSalesListView(AfterSalesAccessView):
    required_feature = "after_sales"
    template_name = "common/after_sales/list.html"


class DolphinAfterSalesDetailView(AfterSalesAccessView, ScopedDetailView):
    required_feature = "after_sales"
    template_name = "common/after_sales/detail.html"
    object_id_kwarg = "request_id"
    context_id_name = "after_sales_request_id"
    not_found_title = "پرونده پیدا نشد"
    not_found_message = "پرونده در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return after_sales_requests_for(self.request.user)


class AuditReaderView(ActiveCrmView):
    def dispatch(self, request, *args, **kwargs):
        if not is_crm_identity(request.user):
            return super().dispatch(request, *args, **kwargs)
        if not has_any_capability(request.user, "audit.non_platform", "audit.all"):
            return self.render_to_response(
                self.get_context_data(
                    error_status=403,
                    error_title="دسترسی مجاز نیست",
                    error_message="شما اجازه مشاهده رویدادهای سامانه را ندارید.",
                ),
                status=403,
            )
        return super().dispatch(request, *args, **kwargs)


class DolphinActivityLogListView(AuditReaderView):
    required_feature = "audit_log"
    template_name = "common/activity_logs/list.html"


class DolphinActivityLogDetailView(AuditReaderView, ScopedDetailView):
    required_feature = "audit_log"
    template_name = "common/activity_logs/detail.html"
    object_id_kwarg = "activity_log_id"
    context_id_name = "activity_log_id"

    def scoped_queryset(self):
        return activity_logs_for(self.request.user)


# --- Inventory pages ---------------------------------------------------------

class DolphinWarehouseListView(ActiveCrmView):
    required_feature = "inventory"
    template_name = "common/warehouses/list.html"


class DolphinWarehouseDetailView(ScopedDetailView):
    required_feature = "inventory"
    template_name = "common/warehouses/detail.html"
    object_id_kwarg = "warehouse_id"
    context_id_name = "warehouse_id"
    not_found_title = "انبار پیدا نشد"
    not_found_message = "انبار در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return warehouses_for(self.request.user)


class DolphinStockLevelListView(ActiveCrmView):
    required_feature = "inventory"
    template_name = "common/inventory/stock_levels.html"


class DolphinStockMovementListView(ActiveCrmView):
    required_feature = "inventory"
    template_name = "common/inventory/stock_movements.html"


# --- Commercial document pages ----------------------------------------------

class DolphinOrderListView(ActiveCrmView):
    required_feature = "orders"
    template_name = "common/orders/list.html"


class DolphinOrderDetailView(ScopedDetailView):
    required_feature = "orders"
    template_name = "common/orders/detail.html"
    object_id_kwarg = "order_id"
    context_id_name = "order_id"
    not_found_title = "سفارش پیدا نشد"
    not_found_message = "سفارش در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return orders_for(self.request.user)


class DolphinInvoiceListView(ActiveCrmView):
    required_feature = "invoices"
    template_name = "common/invoices/list.html"


class DolphinInvoiceDetailView(ScopedDetailView):
    required_feature = "invoices"
    template_name = "common/invoices/detail.html"
    object_id_kwarg = "invoice_id"
    context_id_name = "invoice_id"
    not_found_title = "فاکتور پیدا نشد"
    not_found_message = "فاکتور در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return invoices_for(self.request.user)


class PrintableDocumentView(ScopedDetailView):
    """A document rendered for paper: no navigation, no controls, print stylesheet.

    Server-rendered from the stored snapshot rather than assembled by script, so
    what prints is exactly the row. A page that fails to load prints nothing,
    rather than printing a blank form that still looks official.
    """

    def get_document(self):
        raise NotImplementedError

    #: File stem for a downloaded PDF, joined with the document number.
    pdf_name_prefix = "document"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not context.get("error_status"):
            document = self.get_document()
            context["document"] = document
            context["items"] = list(document.items.order_by("line_number"))
            context["taxable_amount"] = document.subtotal_amount - document.discount_amount
            # بند ۹.۲ — the amount stated a second time, in words, so a digit
            # cannot be added to it after signing.
            context["total_in_words"] = amount_in_words(document.total_amount)
            context["status_label"] = DOCUMENT_STATUS_LABELS.get(document.status, document.status)
            settlement = getattr(document, "settlement_status", None)
            if settlement is not None:
                context["settlement_label"] = SETTLEMENT_LABELS.get(settlement, settlement)
        # Offer the download only where the server can really produce one.
        context.setdefault("pdf_available", renderer_is_available())
        return context


class DocumentPdfView(PrintableDocumentView):
    """The same print page, printed by the server instead of by the reader.

    Reusing the template rather than building a second layout is the whole
    point: the PDF cannot drift away from the page that was verified in the
    browser, because there is only one of them.
    """

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        status = getattr(response, "status_code", 200)
        if status != 200:
            # Out of scope or feature disabled: answer exactly as the print
            # page does, so a direct URL leaks nothing the page would not.
            return response
        context = response.context_data
        context.update(pdf_mode=True, inline_css=inline_stylesheet())
        html = render_to_string(self.template_name, context, request=request)
        try:
            payload = render_html_to_pdf(html)
        except PdfRendererBusy:
            # Every render slot is taken. Rendering occupies a whole worker, so
            # refusing here is what keeps the rest of the site answering; the
            # browser's own print button still works meanwhile.
            response = self.render_to_response(
                self.get_context_data(
                    error_status=503,
                    error_title="تولید PDF شلوغ است",
                    error_message="در حال حاضر سند دیگری در حال تولید است. چند لحظه بعد دوباره تلاش کنید یا از دکمه «چاپ / ذخیره PDF» مرورگر استفاده کنید.",
                ),
                status=503,
            )
            response["Retry-After"] = "10"
            return response
        except PdfRendererUnavailable:
            return self.render_to_response(
                self.get_context_data(
                    error_status=503,
                    error_title="تولید PDF در دسترس نیست",
                    error_message="این استقرار موتور تولید PDF ندارد. از دکمه «چاپ / ذخیره PDF» مرورگر استفاده کنید.",
                ),
                status=503,
            )
        document = context["document"]
        pdf = HttpResponse(payload, content_type="application/pdf")
        pdf["Content-Disposition"] = f'attachment; filename="{self.pdf_name_prefix}-{document.number}.pdf"'
        return pdf


class DolphinInvoicePrintView(PrintableDocumentView):
    required_feature = "invoices"
    template_name = "common/invoices/print.html"
    object_id_kwarg = "invoice_id"
    context_id_name = "invoice_id"
    not_found_title = "فاکتور پیدا نشد"
    not_found_message = "فاکتور در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return invoices_for(self.request.user)

    def get_document(self):
        return (
            self.scoped_queryset()
            .select_related("customer", "created_by", "warehouse")
            .prefetch_related("items")
            .get(pk=self.kwargs["invoice_id"])
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if context.get("error_status"):
            return context
        document = context["document"]
        items = context["items"]

        # بند ۹ — the sample invoice prints tax on every line. The stored
        # document has one header tax figure, so the columns are derived and
        # forced to add up to it.
        # The footer comes back from the same computation as the columns, so the
        # two cannot drift: they are the same numbers, already in whole rial.
        context["line_rows"], context["line_totals"] = printed_line_breakdown(
            items=items,
            header_discount=document.discount_amount,
            tax_rate=document.tax_rate,
            tax_amount=document.tax_amount,
        )

        # بند ۲ — both parties as they were frozen at issue. An invoice issued
        # before the snapshot existed, or still a draft, has none; it falls back
        # to the live records so the page never prints an empty identity block.
        customer = document.customer
        phone = customer.phones.filter(is_active=True).order_by("-is_primary", "id").first()
        context["buyer"] = {
            "name": document.buyer_name or customer.full_name,
            "national_id": document.buyer_national_id or customer.national_id,
            "economic_code": document.buyer_economic_code or customer.economic_code,
            "address": document.buyer_address or customer.address,
            "postal_code": document.buyer_postal_code or customer.postal_code,
            "city": document.buyer_city or customer.city,
            "phone": document.buyer_phone or (phone.raw_phone if phone else ""),
        }
        context["seller"] = {
            "name": document.seller_name or settings.SELLER_LEGAL_NAME,
            "registration_number": (
                document.seller_registration_number or settings.SELLER_REGISTRATION_NUMBER
            ),
            "national_id": document.seller_national_id or settings.SELLER_NATIONAL_ID,
            "economic_code": document.seller_economic_code or settings.SELLER_ECONOMIC_CODE,
            "address": document.seller_address or settings.SELLER_ADDRESS,
            "postal_code": document.seller_postal_code or settings.SELLER_POSTAL_CODE,
            "city": document.seller_city or settings.SELLER_CITY,
            "phone": document.seller_phone or settings.SELLER_PHONE,
        }
        # A snapshot is what makes the document evidence; say so when there
        # isn't one rather than letting live data pass as frozen.
        context["identity_is_snapshot"] = bool(document.buyer_name)
        return context


class DolphinInvoicePdfView(DocumentPdfView, DolphinInvoicePrintView):
    pdf_name_prefix = "invoice"


# --- Money pages -------------------------------------------------------------

class PaymentDeskView(ActiveCrmView):
    """Pages that handle money: `payments.company` only, never a Sales Agent."""

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(request.user, "payments.company"):
            return self.render_to_response(self.get_context_data(
                error_status=403, error_title="دسترسی مجاز نیست",
                error_message="شما اجازه کار با دریافت‌ها را ندارید.",
            ), status=403)
        return super().dispatch(request, *args, **kwargs)


class DolphinPaymentListView(PaymentDeskView):
    """Money coming in.

    Receipts and disbursements are the same document read in two directions, so
    they share one template and one page handler. What differs is the wording —
    a receipt names a customer, a disbursement names whoever was paid — and that
    is carried in the context rather than duplicated into a second copy of two
    hundred lines of markup that would then drift.
    """

    required_feature = "payments"
    template_name = "common/payments/list.html"
    direction = "receipt"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["payment_direction"] = self.direction
        return context


class DolphinDisbursementListView(DolphinPaymentListView):
    """Money going out. The same desk, facing the other way."""

    direction = "disbursement"


class DolphinPaymentDetailView(PaymentDeskView, ScopedDetailView):
    required_feature = "payments"
    template_name = "common/payments/detail.html"
    #: Whether this reader may correct a recorded document. The platform admin
    #: may; everyone else sees the same page read-only. Checked here as well as
    #: in the API — the field being editable on screen is a convenience, never
    #: the authorisation.
    
    object_id_kwarg = "payment_id"
    context_id_name = "payment_id"
    not_found_title = "دریافت پیدا نشد"
    not_found_message = "دریافت در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return payments_for(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_edit_payment"] = (
            self.request.user.role == User.Role.PLATFORM_ADMIN
        )
        # Which desk this document belongs to, resolved here rather than left to
        # the script. The page is titled and the sidebar is lit before any
        # request completes, so a disbursement opened from «پرداخت‌ها» must not
        # spend its first paint calling itself a receipt and lighting the
        # «دریافت‌ها» entry — which is what it did, because both desks share this
        # one route and the nav matches by URL prefix.
        context["payment_direction"] = (
            self.scoped_queryset()
            .filter(pk=self.kwargs[self.object_id_kwarg])
            .values_list("direction", flat=True)
            .first()
        )
        return context


class DolphinChequeListView(PaymentDeskView):
    required_feature = "payments"
    template_name = "common/payments/cheques.html"


class DolphinInstallmentListView(PaymentDeskView):
    required_feature = "payments"
    template_name = "common/payments/installments.html"


class DolphinCustomerLedgerView(ActiveCrmView):
    required_feature = "customer_ledger"
    template_name = "common/reports/customer_ledger.html"

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(
            request.user, "ledger.company", "ledger.own"
        ):
            return self.render_to_response(self.get_context_data(
                error_status=403, error_title="دسترسی مجاز نیست",
                error_message="شما اجازه مشاهده دفتر حساب مشتری را ندارید.",
            ), status=403)
        return super().dispatch(request, *args, **kwargs)


# --- Financial report pages --------------------------------------------------

class CompanyReportView(ActiveCrmView):
    """Money reports need `reports.company`; `reports.own` is not enough."""

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(request.user, "reports.company"):
            return self.render_to_response(self.get_context_data(
                error_status=403, error_title="دسترسی مجاز نیست",
                error_message="شما اجازه مشاهده این گزارش را ندارید.",
            ), status=403)
        return super().dispatch(request, *args, **kwargs)


class DolphinReceivablesReportView(CompanyReportView):
    required_feature = "invoices"
    template_name = "common/reports/receivables.html"


class DolphinProfitReportView(CompanyReportView):
    required_feature = "invoices"
    template_name = "common/reports/profit.html"


class DolphinStockValuationReportView(CompanyReportView):
    required_feature = "inventory"
    template_name = "common/reports/stock_valuation.html"
