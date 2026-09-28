import os

from django.core.wsgi import get_wsgi_application
from django.urls import get_resolver


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

# Force the URL resolver to build now, at worker start, instead of lazily on
# whichever request happens to arrive first (Django's normal behaviour).
# Building it imports every view module the urlconf reaches — including
# `drf_spectacular`, pulled in wherever a view carries `@extend_schema` — and
# that import alone costs several hundred ms (measured: ~0.6s). Paid here,
# once per worker at boot, a user's first click of a session never eats it;
# left lazy, whoever's request happens to be first on a freshly started
# worker — often the topbar reminder bell, since it is the first thing a
# session touches — pays the whole cost and it reads as "reminders is slow".
get_resolver().url_patterns

