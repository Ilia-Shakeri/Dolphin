"""`collectstatic` that collects only what a served page can request.

The purchased theme's tree is the static root, and most of it is demonstration
material: ~46MB of stock photography and illustrations, icon families the UI
does not use, the LTR builds of the RTL bundles, and per-demo scripts. None of
it is reachable from a served page, and all of it would otherwise be copied into
the release image.

Django's `collectstatic` takes ignore patterns only on the command line, so a
settings constant alone does nothing — which is exactly what
`STATICFILES_COLLECT_IGNORE` was doing before this command existed. Overriding
the command applies the same list everywhere it runs: development, Compose, and
the image build, with no call site to keep in sync.

`--ignore` on the command line still works and adds to these defaults.
"""

from django.conf import settings
from django.contrib.staticfiles.management.commands.collectstatic import (
    Command as CollectStaticCommand,
)


class Command(CollectStaticCommand):
    def handle(self, **options):
        configured = list(getattr(settings, "STATICFILES_COLLECT_IGNORE", []))
        supplied = list(options.get("ignore_patterns") or [])
        # The caller's patterns are additive; the deployment's own exclusions
        # are not something an invocation should be able to forget.
        options["ignore_patterns"] = supplied + [
            pattern for pattern in configured if pattern not in supplied
        ]
        return super().handle(**options)
