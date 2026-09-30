"""The panel's JavaScript modules, addressed by name and cached by release.

The application script is a tree of ES modules under `common/static/common/js/`
(`core/`, `ui/`, `shell/`, `features/`). A module imports another by a bare
specifier such as `dolphin/core/api.js`; the browser resolves it through the
import map this tag prints. Every entry carries the release as a query
(`?v=…`), which is what lets nginx keep a module for a year and lets a new
release reach a returning reader: a relative import could not carry the query,
so each module would be revalidated on every page.
"""

import json
from functools import lru_cache
from pathlib import Path

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe

register = template.Library()

STATIC_ROOT_NAME = "common/js"
MODULE_ROOT = Path(__file__).resolve().parents[1] / "static" / "common" / "js"


@lru_cache(maxsize=1)
def module_paths():
    """Every module, relative to the module root, in a stable order."""
    return tuple(sorted(path.relative_to(MODULE_ROOT).as_posix() for path in MODULE_ROOT.rglob("*.js")))


@register.simple_tag
def dolphin_import_map():
    version = settings.DOLPHIN_VERSION
    imports = {
        f"dolphin/{path}": f"{static(f'{STATIC_ROOT_NAME}/{path}')}?v={version}"
        for path in module_paths()
    }
    # `<` is escaped so no module path can ever close the script element early;
    # the closing braces sit on separate lines so the page never carries the
    # `}}` sequence that a template-leak check looks for.
    inner = json.dumps(imports, separators=(",", ":")).replace("<", "\\u003c")
    return mark_safe(f'<script type="importmap">{{"imports":{inner}\n}}</script>')


@register.simple_tag
def dolphin_entry_url():
    return f"{static(f'{STATIC_ROOT_NAME}/main.js')}?v={settings.DOLPHIN_VERSION}"
