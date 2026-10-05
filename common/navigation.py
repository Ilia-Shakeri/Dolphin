"""The panel's navigation, in one place (2.40.0).

Every menu group and link, its label, icon, page and the controls that show
it, is declared here once. The sidebar (`base.html` through the
`sidebar_navigation` tag), page titles and breadcrumbs (`nav_label`), and the
global search's group names read this registry, so a page is called the same
thing everywhere.

The order is the order work flows through the business: campaign → lead →
customer → invoice → supply → money, then after-sales, shipping,
communication, reports and administration.

Visibility here is display only. Every page and API checks the same feature
and capability again on the server; hiding a link is never authorisation.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    module: str
    label: str
    url_name: str
    show: object = None  # callable(ctx) -> bool; None = always

    def visible(self, ctx):
        return True if self.show is None else bool(self.show(ctx))


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    icon: str
    icon_paths: int
    items: tuple = field(default_factory=tuple)
    #: A group of one link renders as that link, with the group's icon.
    label_for: object = None  # callable(ctx) -> str, for a context-dependent caption

    def caption(self, ctx):
        return self.label_for(ctx) if self.label_for else self.label


def _feature_and(feature, *capabilities):
    def show(ctx):
        return feature in ctx["features"] and any(c in ctx["capabilities"] for c in capabilities)

    return show


def _flag(name, feature=None):
    def show(ctx):
        return bool(ctx.get(name)) and (feature is None or feature in ctx["features"])

    return show


def _admin_caption(ctx):
    if ctx.get("is_platform_navigation"):
        return "مدیریت پلتفرم"
    if ctx.get("role") == "sales_manager":
        return "مدیریت تیم فروش"
    return "مدیریت فنی"


GROUPS = (
    Group("dashboard", "داشبورد", "di-element-11", 4, (Item("dashboard", "داشبورد", "common_ui:home"),)),
    Group("campaigns", "کمپین‌ها", "di-send", 2, (
        Item("campaigns", "فهرست کمپین‌ها", "common_ui:campaigns", _feature_and("campaigns", "campaigns.scoped", "campaigns.company")),
        Item("campaign-results", "نتایج کمپین‌ها", "common_ui:campaign-results",
             lambda ctx: "campaigns" in ctx["features"] and bool({"campaign_results.scoped", "campaign_results.company"} & ctx["capabilities"])),
        Item("campaign-analytics", "تحلیل کمپین‌ها", "common_ui:campaign-analytics",
             lambda ctx: "campaigns" in ctx["features"] and "campaigns.analytics" in ctx["capabilities"]),
    )),
    Group("leads", "سرنخ‌ها و پیگیری", "di-phone", 2, (
        Item("leads", "سرنخ‌ها", "common_ui:leads", _feature_and("leads", "leads.scoped", "leads.company")),
        Item("lead-calendar", "تقویم پیگیری", "common_ui:lead-calendar", _feature_and("leads", "leads.scoped", "leads.company")),
        Item("lead-board", "تابلوی سرنخ‌ها", "common_ui:lead-board",
             lambda ctx: "lead_kanban" in ctx["features"] and _feature_and("leads", "leads.scoped", "leads.company")(ctx)),
        Item("interactions", "تماس‌ها", "common_ui:interactions", _feature_and("leads", "interactions.scoped", "interactions.company")),
    )),
    Group("customers", "مشتریان", "di-profile-user", 4, (
        Item("customers", "مشتریان", "common_ui:customers", _feature_and("customers", "customers.scoped", "customers.company")),
    )),
    Group("sales", "فروش", "di-document", 2, (
        Item("invoices", "فاکتورها", "common_ui:invoices", _feature_and("invoices", "invoices.scoped", "invoices.company")),
        Item("orders", "درخواست‌های تأمین", "common_ui:orders", _feature_and("orders", "orders.scoped", "orders.company")),
        Item("order-board", "تابلوی تأمین", "common_ui:order-board", _feature_and("order_kanban", "orders.scoped", "orders.company")),
        # The retired campaign-result records: read and cancel only (2.39.20).
        Item("sales", "بایگانی فروش‌های قدیمی", "common_ui:sales", _feature_and("sales", "sales.own", "sales.company")),
    )),
    Group("inventory", "انبار و کالا", "di-package", 3, (
        Item("stock-levels", "موجودی کالا", "common_ui:stock-levels", _flag("can_read_inventory", "inventory")),
        Item("warehouses", "انبارها", "common_ui:warehouses", _flag("can_read_inventory", "inventory")),
        Item("stock-movements", "گردش انبار", "common_ui:stock-movements", _flag("can_read_inventory", "inventory")),
        Item("products", "محصولات", "common_ui:products", _feature_and("products", "products.read", "products.manage")),
        Item("product-categories", "دسته‌بندی محصولات", "common_ui:product-categories",
             _feature_and("products", "product_categories.read", "product_categories.manage")),
    )),
    Group("finance", "مالی", "di-wallet", 4, (
        Item("payments", "دریافت‌ها", "common_ui:payments", _flag("can_handle_payments", "payments")),
        Item("disbursements", "پرداخت‌ها", "common_ui:disbursements", _flag("can_handle_payments", "payments")),
        Item("cheques", "چک‌ها", "common_ui:cheques",
             lambda ctx: "cheques" in ctx["features"] and _flag("can_handle_payments", "payments")(ctx)),
        Item("installments", "اقساط", "common_ui:installments", _flag("can_handle_payments", "payments")),
    )),
    Group("after_sales", "پس از فروش", "di-shield-tick", 2, (
        Item("after-sales", "پرونده‌های خدمات", "common_ui:after-sales", _feature_and("after_sales", "after_sales.assigned", "after_sales.company")),
        Item("after-sales-calendar", "تقویم خدمات پس از فروش", "common_ui:after-sales-calendar",
             _feature_and("after_sales", "after_sales.assigned", "after_sales.company")),
    )),
    Group("shipping", "ارسال و پست", "di-delivery", 5, (
        Item("sales-documents", "رهگیری پستی", "common_ui:sales-documents",
             _feature_and("sales_documents", "sales_documents.scoped", "sales_documents.company")),
        Item("sales-document-report", "گزارش ارسال و پست", "common_ui:sales-document-report",
             lambda ctx: "sales_documents" in ctx["features"] and "reports" in ctx["features"]
             and bool({"reports.own", "reports.company"} & ctx["capabilities"])),
    )),
    Group("communication", "ارتباط", "di-message-text-2", 3, (
        Item("outbound-sms", "ارسال پیامک", "common_ui:outbound-sms", _flag("can_send_sms", "outbound_sms")),
        Item("chat", "گفت‌وگو", "common_ui:chat", lambda ctx: "internal_chat" in ctx["features"]),
        Item("inbound-sms-report", "گزارش پیامک ورودی", "common_ui:inbound-sms-report", _flag("can_view_sms_report", "inbound_sms")),
    )),
    Group("reports", "گزارش‌ها", "di-chart-simple", 4, (
        Item("performance", "عملکرد فروش", "common_ui:user-performance", _feature_and("reports", "reports.own", "reports.company")),
        Item("receivables-report", "مطالبات", "common_ui:receivables-report", _flag("can_view_company_reports", "invoices")),
        Item("profit-report", "سود ناخالص", "common_ui:profit-report", _flag("can_view_company_reports", "invoices")),
        Item("stock-valuation-report", "ارزش موجودی", "common_ui:stock-valuation-report", _flag("can_view_company_reports", "inventory")),
        Item("customer-ledger", "دفتر حساب مشتری", "common_ui:customer-ledger", _flag("can_view_ledger", "customer_ledger")),
    )),
    Group("administration", "مدیریت", "di-setting-2", 2, (
        Item("audit", "رویدادهای سامانه", "common_ui:activity-logs", _flag("can_view_audit")),
        Item("users", "کاربران", "common_ui:users", _flag("can_manage_users")),
        Item("integrations", "یکپارچه‌سازی‌ها", "common_ui:integrations", _flag("can_manage_integrations")),
    ), label_for=_admin_caption),
    Group("settings", "تنظیمات", "di-setting-3", 5, (Item("settings", "تنظیمات", "common_ui:settings"),)),
)

#: In-page tab bars (2.40.0): the views of one subject, each its own page/URL.
TAB_SETS = {
    "campaigns": ("campaigns", "campaign-results", "campaign-analytics"),
    "leads": ("leads", "lead-calendar", "lead-board"),
    "supply": ("orders", "order-board"),
    "after_sales": ("after-sales", "after-sales-calendar"),
}

#: url name -> menu label, for page titles, breadcrumbs and search.
LABELS = {item.url_name: item.label for group in GROUPS for item in group.items}
#: module -> menu label.
MODULE_LABELS = {item.module: item.label for group in GROUPS for item in group.items}


def page_tabs(ctx, key, current_module):
    """The tabs of one tab set this reader may open, with the current one."""
    from django.urls import reverse

    items = {item.module: item for group in GROUPS for item in group.items}
    tabs = [items[module] for module in TAB_SETS[key] if items[module].visible(ctx)]
    return [
        {"module": item.module, "label": item.label, "url": reverse(item.url_name), "current": item.module == current_module}
        for item in tabs
    ]


def navigation_context(ctx):
    """The groups and links one reader is shown, ready for the template."""
    from django.urls import reverse

    shown = []
    for group in GROUPS:
        items = [item for item in group.items if item.visible(ctx)]
        if not items:
            continue
        caption = group.caption(ctx)
        links = [{"module": item.module, "label": item.label, "url": reverse(item.url_name)} for item in items]
        if group.key == "administration" and ctx.get("user_admin_label"):
            for link in links:
                if link["module"] == "users":
                    link["label"] = ctx["user_admin_label"]
        shown.append({
            "key": group.key, "label": caption, "icon": group.icon, "icon_paths": range(1, group.icon_paths + 1),
            "single": len(group.items) == 1, "links": links,
        })
    return shown
