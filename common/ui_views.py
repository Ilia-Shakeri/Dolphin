from django.contrib.auth import SESSION_KEY, logout
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView

from accounts.access import capabilities_for, crm_identities, has_any_capability, is_crm_identity
from accounts.models import User
from auditlog.selectors import activity_logs_for
from aftersales.selectors import after_sales_requests_for
from sales.selectors import customers_for, interactions_for, leads_for, products_for, sales_documents_for, sales_for


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
class ActiveCrmView(TemplateView):
    def dispatch(self, request, *args, **kwargs):
        if not is_crm_identity(request.user):
            if request.user.is_authenticated or SESSION_KEY in request.session:
                logout(request)
            return redirect("common_ui:login")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        capabilities = capabilities_for(self.request.user)
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
        context["can_reassign_leads"] = context["can_deactivate_customers"]
        context["can_manage_products"] = context["can_deactivate_customers"]
        context["can_cancel_sales"] = context["can_deactivate_customers"]
        context["can_manage_sales_documents"] = context["can_deactivate_customers"]
        context["can_manage_after_sales"] = "after_sales.manage" in capabilities
        context["can_view_company_reports"] = "reports.company" in capabilities
        context["can_view_audit"] = bool({"audit.non_platform", "audit.all"}.intersection(capabilities))
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
            User.Role.SALES_MANAGER: ("پنل مدیر فروشگاه", "نمای سراسری کسب‌وکار و مدیریت بازاریابان این استقرار"),
            User.Role.SALES_AGENT: ("میز کار بازاریاب", "سرنخ‌های تخصیص‌یافته، تماس‌های دستی و عملکرد خود شما"),
            User.Role.COMPANY_IT: ("پنل مدیر فنی مشتری", "مدیریت فنی کاربران غیرپلتفرم و دسترسی عملیاتی شرکت"),
        }[role]
        if role == User.Role.SALES_AGENT and self.request.user.workstream == User.Workstream.AFTER_SALES:
            dashboard = (
                "میز کار خدمات پس از فروش",
                "پرونده‌های تخصیص‌یافته و اقدام‌های ثبت‌شده شما",
            )
        widgets = []

        def add(capability, label, value, url_name):
            if capability in capabilities:
                widgets.append({"capability": capability, "label": label, "value": value, "url_name": url_name})

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
            })
        if context["can_view_audit"]:
            widgets.append({
                "capability": "audit.all" if "audit.all" in capabilities else "audit.non_platform",
                "label": "رویدادهای قابل مشاهده",
                "value": activity_logs_for(self.request.user).count(),
                "url_name": "common_ui:activity-logs",
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
        return context


class KarizCustomerListView(ActiveCrmView):
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
    template_name = "common/customers/detail.html"
    object_id_kwarg = "customer_id"
    context_id_name = "customer_id"
    not_found_title = "مشتری پیدا نشد"
    not_found_message = "مشتری در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return customers_for(self.request.user)


class KarizLeadListView(ActiveCrmView):
    template_name = "common/leads/list.html"


class KarizLeadDetailView(ScopedDetailView):
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
    template_name = "common/interactions/list.html"


class KarizInteractionDetailView(ScopedDetailView):
    template_name = "common/interactions/detail.html"
    object_id_kwarg = "interaction_id"
    context_id_name = "interaction_id"
    not_found_title = "تماس پیدا نشد"
    not_found_message = "تماس در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return interactions_for(self.request.user)


class KarizProductListView(ActiveCrmView):
    template_name = "common/products/list.html"


class KarizProductDetailView(ScopedDetailView):
    template_name = "common/products/detail.html"
    object_id_kwarg = "product_id"
    context_id_name = "product_id"

    def scoped_queryset(self):
        return products_for(self.request.user)


class KarizSaleListView(ActiveCrmView):
    template_name = "common/sales/list.html"


class KarizSaleDetailView(ScopedDetailView):
    template_name = "common/sales/detail.html"
    object_id_kwarg = "sale_id"
    context_id_name = "sale_id"

    def scoped_queryset(self):
        return sales_for(self.request.user)


class KarizSalesDocumentListView(ActiveCrmView):
    template_name = "common/sales_documents/list.html"


class KarizSalesDocumentDetailView(ScopedDetailView):
    template_name = "common/sales_documents/detail.html"
    object_id_kwarg = "document_id"
    context_id_name = "document_id"
    not_found_title = "سند فروش پیدا نشد"
    not_found_message = "سند فروش در محدوده دسترسی شما وجود ندارد."

    def scoped_queryset(self):
        return sales_documents_for(self.request.user)


class KarizUserPerformanceView(ActiveCrmView):
    template_name = "common/reports/user_performance.html"

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(request.user, "reports.own", "reports.company"):
            return self.render_to_response(self.get_context_data(
                error_status=403, error_title="دسترسی مجاز نیست",
                error_message="شما اجازه مشاهده این گزارش را ندارید.",
            ), status=403)
        return super().dispatch(request, *args, **kwargs)


class KarizSalesDocumentReportView(ActiveCrmView):
    template_name = "common/reports/sales_documents.html"

    def dispatch(self, request, *args, **kwargs):
        if is_crm_identity(request.user) and not has_any_capability(request.user, "reports.own", "reports.company"):
            return self.render_to_response(self.get_context_data(
                error_status=403, error_title="دسترسی مجاز نیست",
                error_message="شما اجازه مشاهده این گزارش را ندارید.",
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
    template_name = "common/after_sales/list.html"


class KarizAfterSalesDetailView(AfterSalesAccessView, ScopedDetailView):
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
    template_name = "common/activity_logs/list.html"


class KarizActivityLogDetailView(AuditReaderView, ScopedDetailView):
    template_name = "common/activity_logs/detail.html"
    object_id_kwarg = "activity_log_id"
    context_id_name = "activity_log_id"

    def scoped_queryset(self):
        return activity_logs_for(self.request.user)
