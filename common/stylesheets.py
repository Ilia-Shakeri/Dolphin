"""The panel's own stylesheet, kept as ordered layers (2.40.42).

Until 2.40.42 this was one file, `common/dolphin.css`, grown to 6,700 lines.
It is now one file per layer under `common/static/common/css/`, listed below in
cascade order: a later layer wins a tie with an earlier one exactly as a later
rule did in the single sheet, so the split changed no computed style (checked
element by element on every page, in both themes and on a phone). Every page
links the layers in this order (`{% dolphin_stylesheets %}`), the PDF renderer
inlines them in this order, and the tests read them through `stylesheet_text()`.

A new rule goes in the layer that owns its subject. A new layer is added here,
at the place in the cascade it needs — nowhere else lists them.
"""

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "static"

STYLESHEETS = (
    "common/css/tokens.css",  # motion, radius and size tokens
    "common/css/behaviour.css",  # `hidden`, native dialogs, the fixed header
    "common/css/shell.css",  # brand mark, sidebar, header menus, search, chat drawer
    "common/css/login.css",
    "common/css/print.css",  # the printed invoice and quotation
    "common/css/theme-repairs.css",  # selects, list filters, popups, charts, focus
    "common/css/tables-dialogs.css",  # row actions, dialogs, the wizard review step
    "common/css/line-chart-calendar.css",
    "common/css/kanban.css",
    "common/css/map-line-items-tables.css",  # province map, wizard line items, data tables
    "common/css/date-picker.css",
    "common/css/dashboard-editor.css",
    "common/css/components.css",  # scrollbar, postal stepper, integrations, avatars, settings
    "common/css/dashboard-widgets.css",
    "common/css/states.css",  # loading, busy buttons, segmented toggle, reveal
    "common/css/dashboard-grid.css",  # the free grid, widget and KPI cards
    "common/css/refinements.css",  # 2.38–2.40.36 product refinements
    "common/css/platform.css",  # the platform layer (2.40.38) and what followed it
    "common/css/live-record.css",
    "common/css/two-factor.css",
    "common/css/drawers-files.css",  # activity and help drawers, the file manager
)


def stylesheet_paths():
    """Each layer's file in the app directory, in cascade order."""
    return [STATIC_DIR / name for name in STYLESHEETS]


def stylesheet_text():
    """The whole panel stylesheet as one text, in cascade order."""
    return "".join(path.read_text(encoding="utf-8") for path in stylesheet_paths())
