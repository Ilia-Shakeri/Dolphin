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
from billing.selectors import (
    cheques_for,
    quotations_for,
    installment_plans_for,
    invoices_for,
    orders_for,
    payments_for,
)
from inventory.selectors import stock_items_for, stock_movements_for, warehouses_for
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
class KarizLoginView(TemplateView):
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
            {"invoices.company", "orders.company", "quotations.company"}.intersection(capabilities)
        )
        context["can_handle_payments"] = "payments.company" in capabilities
        context["can_view_ledger"] = "ledger.company" in capabilities
        context["can_view_sms_report"] = "sms.company" in capabilities
        context["can_view_audit"] = feature_enabled("audit_log") and bool(
            {"audit.non_platform", "audit.all"}.intersection(capabilities)
        )
        context["is_platform_navigation"] = "dashboard.platform" in capabilities
        return context


class KarizHomeView(ActiveCrmView):
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


class KarizUserListView(UserAdminView):
    template_name = "common/users/list.html"


class KarizUserDetailView(UserAdminView):
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


class KarizCustomerListView(ActiveCrmView):
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


class KarizCustomerDetailView(ScopedDetailView):
    required_feature = "customers"
    template_name = "common/customers/detail.html"
    object_id_kwarg = "customer_id"
    context_id_name = "customer_id"
    not_found_title = "مشتری پیدا نشد"
    not_found_message = "مشتری در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return customers_for(self.request.user)


class KarizLeadListView(ActiveCrmView):
    required_feature = "leads"
    template_name = "common/leads/list.html"


class KarizLeadDetailView(ScopedDetailView):
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


class KarizInteractionListView(ActiveCrmView):
    required_feature = "leads"
    template_name = "common/interactions/list.html"


class KarizInteractionDetailView(ScopedDetailView):
    required_feature = "leads"
    template_name = "common/interactions/detail.html"
    object_id_kwarg = "interaction_id"
    context_id_name = "interaction_id"
    not_found_title = "تماس پیدا نشد"
    not_found_message = "تماس در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return interactions_for(self.request.user)


class KarizProductListView(ActiveCrmView):
    required_feature = "products"
    template_name = "common/products/list.html"


class KarizProductCategoryListView(ActiveCrmView):
    required_feature = "products"
    template_name = "common/product_categories/list.html"


class KarizProductCategoryDetailView(ScopedDetailView):
    required_feature = "products"
    template_name = "common/product_categories/detail.html"
    object_id_kwarg = "category_id"
    context_id_name = "category_id"
    not_found_title = "دسته‌بندی پیدا نشد"
    not_found_message = "دسته‌بندی در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return product_categories_for(self.request.user)


class KarizProductDetailView(ScopedDetailView):
    required_feature = "products"
    template_name = "common/products/detail.html"
    object_id_kwarg = "product_id"
    context_id_name = "product_id"

    def scoped_queryset(self):
        return products_for(self.request.user)


class KarizSaleListView(ActiveCrmView):
    required_feature = "sales"
    template_name = "common/sales/list.html"


class KarizSaleDetailView(ScopedDetailView):
    required_feature = "sales"
    template_name = "common/sales/detail.html"
    object_id_kwarg = "sale_id"
    context_id_name = "sale_id"

    def scoped_queryset(self):
        return sales_for(self.request.user)


class KarizSalesDocumentListView(ActiveCrmView):
    required_feature = "sales_documents"
    template_name = "common/sales_documents/list.html"


class KarizSalesDocumentDetailView(ScopedDetailView):
    required_feature = "sales_documents"
    template_name = "common/sales_documents/detail.html"
    object_id_kwarg = "document_id"
    context_id_name = "document_id"
    not_found_title = "سند فروش پیدا نشد"
    not_found_message = "سند فروش در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return sales_documents_for(self.request.user)


class KarizUserPerformanceView(ActiveCrmView):
    required_feature = "reports"
    template_name = "common/reports/user_performance.html"

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(request.user, "reports.own", "reports.company"):
            return self.render_to_response(self.get_context_data(
                error_status=403, error_title="دسترسی مجاز نیست",
                error_message="شما اجازه مشاهده این گزارش را ندارید.",
            ), status=403)
        return super().dispatch(request, *args, **kwargs)


class KarizSalesDocumentReportView(ActiveCrmView):
    required_feature = "sales_documents"
    template_name = "common/reports/sales_documents.html"

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(request.user, "reports.own", "reports.company"):
            return self.render_to_response(self.get_context_data(
                error_status=403, error_title="دسترسی مجاز نیست",
                error_message="شما اجازه مشاهده این گزارش را ندارید.",
            ), status=403)
        return super().dispatch(request, *args, **kwargs)


class KarizInboundSMSReportView(ActiveCrmView):
    required_feature = "inbound_sms"
    template_name = "common/reports/inbound_sms.html"

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(request.user, "sms.company"):
            return self.render_to_response(self.get_context_data(
                error_status=403, error_title="دسترسی مجاز نیست",
                error_message="شما اجازه مشاهده گزارش پیامک ورودی را ندارید.",
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


class KarizAfterSalesListView(AfterSalesAccessView):
    required_feature = "after_sales"
    template_name = "common/after_sales/list.html"


class KarizAfterSalesDetailView(AfterSalesAccessView, ScopedDetailView):
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


class KarizActivityLogListView(AuditReaderView):
    required_feature = "audit_log"
    template_name = "common/activity_logs/list.html"


class KarizActivityLogDetailView(AuditReaderView, ScopedDetailView):
    required_feature = "audit_log"
    template_name = "common/activity_logs/detail.html"
    object_id_kwarg = "activity_log_id"
    context_id_name = "activity_log_id"

    def scoped_queryset(self):
        return activity_logs_for(self.request.user)


# --- Inventory pages ---------------------------------------------------------

class KarizWarehouseListView(ActiveCrmView):
    required_feature = "inventory"
    template_name = "common/warehouses/list.html"


class KarizWarehouseDetailView(ScopedDetailView):
    required_feature = "inventory"
    template_name = "common/warehouses/detail.html"
    object_id_kwarg = "warehouse_id"
    context_id_name = "warehouse_id"
    not_found_title = "انبار پیدا نشد"
    not_found_message = "انبار در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return warehouses_for(self.request.user)


class KarizStockLevelListView(ActiveCrmView):
    required_feature = "inventory"
    template_name = "common/inventory/stock_levels.html"


class KarizStockMovementListView(ActiveCrmView):
    required_feature = "inventory"
    template_name = "common/inventory/stock_movements.html"


# --- Commercial document pages ----------------------------------------------

class KarizQuotationListView(ActiveCrmView):
    required_feature = "quotations"
    template_name = "common/quotations/list.html"


class KarizQuotationDetailView(ScopedDetailView):
    required_feature = "quotations"
    template_name = "common/quotations/detail.html"
    object_id_kwarg = "quotation_id"
    context_id_name = "quotation_id"
    not_found_title = "پیش‌فاکتور پیدا نشد"
    not_found_message = "پیش‌فاکتور در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return quotations_for(self.request.user)


class KarizOrderListView(ActiveCrmView):
    required_feature = "orders"
    template_name = "common/orders/list.html"


class KarizOrderDetailView(ScopedDetailView):
    required_feature = "orders"
    template_name = "common/orders/detail.html"
    object_id_kwarg = "order_id"
    context_id_name = "order_id"
    not_found_title = "سفارش پیدا نشد"
    not_found_message = "سفارش در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return orders_for(self.request.user)


class KarizInvoiceListView(ActiveCrmView):
    required_feature = "invoices"
    template_name = "common/invoices/list.html"


class KarizInvoiceDetailView(ScopedDetailView):
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


class KarizQuotationPrintView(PrintableDocumentView):
    required_feature = "quotations"
    template_name = "common/quotations/print.html"
    object_id_kwarg = "quotation_id"
    context_id_name = "quotation_id"
    not_found_title = "پیش‌فاکتور پیدا نشد"
    not_found_message = "پیش‌فاکتور در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return quotations_for(self.request.user)

    def get_document(self):
        return (
            self.scoped_queryset()
            .select_related("customer", "created_by")
            .prefetch_related("items")
            .get(pk=self.kwargs["quotation_id"])
        )


class KarizInvoicePrintView(PrintableDocumentView):
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


class KarizQuotationPdfView(DocumentPdfView, KarizQuotationPrintView):
    pdf_name_prefix = "quotation"


class KarizInvoicePdfView(DocumentPdfView, KarizInvoicePrintView):
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


class KarizPaymentListView(PaymentDeskView):
    required_feature = "payments"
    template_name = "common/payments/list.html"


class KarizPaymentDetailView(PaymentDeskView, ScopedDetailView):
    required_feature = "payments"
    template_name = "common/payments/detail.html"
    object_id_kwarg = "payment_id"
    context_id_name = "payment_id"
    not_found_title = "دریافت پیدا نشد"
    not_found_message = "دریافت در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return payments_for(self.request.user)


class KarizChequeListView(PaymentDeskView):
    required_feature = "payments"
    template_name = "common/payments/cheques.html"


class KarizInstallmentListView(PaymentDeskView):
    required_feature = "payments"
    template_name = "common/payments/installments.html"


class KarizCustomerLedgerView(ActiveCrmView):
    required_feature = "customer_ledger"
    template_name = "common/reports/customer_ledger.html"

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(request.user, "ledger.company"):
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


class KarizReceivablesReportView(CompanyReportView):
    required_feature = "invoices"
    template_name = "common/reports/receivables.html"


class KarizProfitReportView(CompanyReportView):
    required_feature = "invoices"
    template_name = "common/reports/profit.html"


class KarizStockValuationReportView(CompanyReportView):
    required_feature = "inventory"
    template_name = "common/reports/stock_valuation.html"
