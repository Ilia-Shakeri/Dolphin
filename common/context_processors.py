"""Values every rendered page needs, regardless of which view produced it."""

from django.conf import settings

#: The cookie `KTToggle` writes when the sidebar is collapsed. The name is
#: `data-kt-` plus the toggle's `data-kt-toggle-name`, and it is the vendor's
#: own contract — their markup expects the server to read it back and stamp the
#: attribute on `<body>` before the page paints.
SIDEBAR_MINIMIZE_COOKIE = "data-kt-app-sidebar-minimize"


def sidebar_state(request):
    """Whether the sidebar should render collapsed.

    Read on the server rather than restored by script on load. This panel does
    full page loads between screens, so a collapsed sidebar would otherwise
    paint open and then snap shut on every single navigation — the flicker is
    the whole reason the theme designed it this way.
    """
    return {
        "sidebar_minimized": request.COOKIES.get(SIDEBAR_MINIMIZE_COOKIE) == "on",
    }


def product_version(request):
    """The running version, for the footer.

    A context processor rather than a base-view mixin because the footer lives
    in `base.html` and every template extends it — including the login page and
    the error pages, which are rendered by views that share no base class.
    """
    return {"forooshbin_version": settings.FOROOSHBIN_VERSION}
