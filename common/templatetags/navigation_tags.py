"""The sidebar and page labels from `common.navigation` (2.40.0)."""

from django import template

from common.navigation import LABELS, navigation_context

register = template.Library()

#: The page-context flags the registry's visibility rules read.
FLAGS = (
    "can_handle_payments", "can_read_inventory", "can_manage_inventory", "can_send_sms",
    "can_view_company_reports", "can_view_ledger", "can_view_sms_report", "can_view_audit",
    "can_manage_users", "can_manage_integrations", "is_platform_navigation", "user_admin_label",
)


@register.simple_tag(takes_context=True)
def sidebar_navigation(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    ctx = {
        "features": set(context.get("features") or ()),
        "capabilities": set(context.get("capabilities") or ()),
        "role": getattr(user, "role", ""),
        **{name: context.get(name) for name in FLAGS},
    }
    return navigation_context(ctx)


@register.simple_tag(takes_context=True)
def page_tabs(context, key, current):
    """A tab bar over the views of one subject (2.40.0). Each tab is a link to
    its own URL, so a view stays shareable and the back button works; the
    bar is `role="tablist"` and arrow keys move between tabs (`shell/nav.js`).
    Nothing is drawn when the reader may open fewer than two of them."""
    from django.utils.html import format_html, format_html_join

    from common.navigation import page_tabs as tabs_for

    request = context.get("request")
    user = getattr(request, "user", None)
    ctx = {
        "features": set(context.get("features") or ()),
        "capabilities": set(context.get("capabilities") or ()),
        "role": getattr(user, "role", ""),
        **{name: context.get(name) for name in FLAGS},
    }
    tabs = tabs_for(ctx, key, current)
    if len(tabs) < 2:
        return ""
    links = format_html_join(
        "",
        '<a class="nav-link{}" href="{}" role="tab" aria-selected="{}" tabindex="{}"{}>{}</a>',
        (
            (" active" if tab["current"] else "", tab["url"], "true" if tab["current"] else "false",
             "0" if tab["current"] else "-1", format_html(' aria-current="page"') if tab["current"] else "", tab["label"])
            for tab in tabs
        ),
    )
    return format_html(
        '<nav class="dolphin-page-tabs nav nav-pills nav-pills-custom gap-2 mb-5" role="tablist" aria-label="{}" data-page-tabs>{}</nav>',
        "نماهای این بخش", links,
    )


@register.simple_tag
def nav_label(url_name):
    """The menu label of a page, so its title and breadcrumb read the same."""
    return LABELS.get(url_name, "")
