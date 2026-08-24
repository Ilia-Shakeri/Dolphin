"""Values every rendered page needs, regardless of which view produced it."""

from django.conf import settings


def product_version(request):
    """The running version, for the footer.

    A context processor rather than a base-view mixin because the footer lives
    in `base.html` and every template extends it — including the login page and
    the error pages, which are rendered by views that share no base class.
    """
    return {"forooshbin_version": settings.FOROOSHBIN_VERSION}
