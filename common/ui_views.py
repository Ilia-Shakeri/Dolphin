from django.contrib.auth import SESSION_KEY, logout
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView

from accounts.access import crm_identities, is_crm_identity
from accounts.models import User
from auditlog.selectors import activity_logs_for
from sales.selectors import customers_for, interactions_for, leads_for, products_for, sales_for


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
        context["role_label"] = ROLE_LABELS[self.request.user.role]
        context["can_manage_users"] = self.request.user.role in {
            User.Role.COMPANY_IT,
            User.Role.PLATFORM_ADMIN,
        }
        context["can_deactivate_customers"] = self.request.user.role in {
            User.Role.SALES_MANAGER,
            User.Role.COMPANY_IT,
            User.Role.PLATFORM_ADMIN,
        }
        context["can_reassign_leads"] = context["can_deactivate_customers"]
        context["can_manage_products"] = context["can_deactivate_customers"]
        context["can_cancel_sales"] = context["can_deactivate_customers"]
        context["can_view_company_reports"] = self.request.user.role != User.Role.SALES_AGENT
        context["can_view_audit"] = self.request.user.role in {
            User.Role.COMPANY_IT,
            User.Role.PLATFORM_ADMIN,
        }
        return context


class KarizHomeView(ActiveCrmView):
    template_name = "common/home.html"


class UserAdminView(ActiveCrmView):
    def dispatch(self, request, *args, **kwargs):
        if not is_crm_identity(request.user):
            if request.user.is_authenticated or SESSION_KEY in request.session:
                logout(request)
            return redirect("common_ui:login")
        if request.user.role not in {User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}:
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
        if request.user.role == User.Role.COMPANY_IT:
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


class KarizUserPerformanceView(ActiveCrmView):
    template_name = "common/reports/user_performance.html"


class AuditReaderView(ActiveCrmView):
    def dispatch(self, request, *args, **kwargs):
        if not is_crm_identity(request.user):
            return super().dispatch(request, *args, **kwargs)
        if request.user.role not in {User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}:
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
