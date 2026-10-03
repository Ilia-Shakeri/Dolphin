"""A small local web form over `sign_deployment_manifest.py` and
`new_deployment.py` (PROFILE-001, Option C) — tick features and fill in one
deployment's identity in a browser instead of running two CLI tools by hand.
This is "Level 1 + Level 2" of the mini-app idea recorded in
`DOLPHIN_FEATURE_MAP_AND_ROADMAP.md` §6: a form that builds a signed manifest
and, optionally, a matching `.env` draft — still no SSH, no server access, no
customer host ever reachable from here.

There is still no "brand colour" field, even though the §6 sketch names one:
no setting in this codebase reads a per-deployment brand colour (see
`CLAUDE.md`'s Branding section — the fixed Dolphin / دلفین identifiers that
rule covers are the *engineering* names, e.g. `dolphin.css`, never the
*rendered* name/logo, which is exactly what `custom_branding` now controls).
A customer's own name and logo (2026-09-03, `common.branding`) is instead a
feature like any other: this form's checklist toggles `custom_branding` on
or off exactly like `customers` or `inventory`, and — once on — the
deployment's own Platform Admin sets the actual name/logo from inside their
own panel (`/branding/`), not from here. This tool never touches that value;
it only decides whether the option exists for that deployment at all.

There is no "manage every deployment's config from one dashboard" feature
either, for the same reason `.env` regeneration already draws a line at
files: every change this tool makes reaches a customer's server only as a
file the operator hands over and installs there — never a live push over a
network this tool holds open to that server (see the console's own warning
banner). "Modular and remotely configurable" in the product sense is this:
re-tick the features a customer should have, sign a fresh manifest, deliver
it — the same three steps regardless of which feature changed.

Same platform-owner-only boundary as `sign_deployment_manifest.py`, and for
the same reason: whoever runs this needs the signing private key on the same
machine, which must never be a customer host. Two things enforce that here,
on top of the operator's own judgement:

* This file lives under `scripts/`, which the whole directory is excluded
  from every shipped image by (see `.dockerignore`'s "P0R.4 build-context
  hardening" section) — it can be run from a checkout, never from a running
  deployment.
* The server binds to 127.0.0.1 only, and refuses any request whose `Host`
  header names anything else — so even a machine that turns out to be
  reachable from a wider network than the operator expected cannot reach
  this from outside it.

The private key is read from a local file **path** typed into the form — this
page never accepts a file upload, never logs the key material, and never
echoes it back in any response. Every signing call goes through
`sign_deployment_manifest.build_manifest`, the exact function the CLI uses;
this file adds no cryptography of its own, and reuses `new_deployment.
resolve_features` for the same dependency auto-completion `quickstart.sh`
already relies on, so a feature picked without its dependency does not
produce a manifest the application would refuse to boot from.

Usage:

    python scripts/manifest_builder.py
    # then open http://127.0.0.1:8799/start/ in a browser on the same machine

    python scripts/manifest_builder.py --port 8850 --no-browser

    # A real desktop window instead of a browser tab — the "desktop mini-app"
    # (DOLPHIN_FEATURE_MAP_AND_ROADMAP.md §6). Needs `pip install pywebview`
    # first; nothing else in this repository depends on that package, so it
    # is never installed into a shipped image, only on the operator's own
    # machine. Same server, same routes, same 127.0.0.1-only boundary — this
    # only changes what opens to show them.
    python scripts/manifest_builder.py --desktop

The form also has a "پیش‌نمایش زنده" (live preview) button — tick features,
type the customer's name if they want their own branding, and a real
throwaway instance of this codebase boots on another local port so the
operator can click through exactly what that customer would see before
signing anything for real (`scripts/preview_runner.py`). And once a real
manifest is signed with slug+host filled in, the result offers a single
deployment-bundle zip (manifest + .env draft + a short customer-specific
run sheet) instead of two separate downloads to carry to the server by hand.
"""

import argparse
import base64
import binascii
import html
import io
import json
import os
import re
import sys
import threading
import webbrowser
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

# The same IRANSansWeb the served product uses (`common/static/common/ui/fonts/`, loaded by
# `common/static/common/ui/css/dolphin-theme.rtl.css`) — read from disk and inlined as a data
# URI rather than served from a path, because this tool is a bare
# `BaseHTTPRequestHandler` with no static-file route of its own, and adding
# one for a single font file would be more surface than the font is worth.
# Falls back to the system stack in `_STYLE` below if the checkout this runs
# from is ever missing `common/static/common/ui/` (e.g. a stripped-down copy) rather than
# crashing the whole tool over a typeface.
_FONT_PATH = REPOSITORY_ROOT / "common" / "static" / "common" / "ui" / "fonts" / "IRANSansWeb.woff2"
try:
    _IRANSANS_WOFF2_BASE64 = base64.b64encode(_FONT_PATH.read_bytes()).decode("ascii")
except OSError:
    _IRANSANS_WOFF2_BASE64 = ""

from common.deployment.pages import feature_page_titles  # noqa: E402
from scripts.console_strings import (  # noqa: E402
    DEFAULT_LANGUAGE,
    FEATURE_GROUPS,
    FEATURE_META,
    L,
    LANGUAGES,
    T,
    normalize_language,
)
from common.deployment.registry import DEFAULT_OFF_FEATURES, FEATURE_DEPENDENCIES, PROFILES, valid_profile_id  # noqa: E402
from scripts import deployment_records, preview_runner  # noqa: E402
from scripts.new_deployment import (  # noqa: E402
    HOST_PATTERN,
    SLUG_PATTERN,
    ProvisioningError,
    env_lines,
    resolve_features,
)
from scripts.sign_deployment_manifest import (  # noqa: E402
    ProvisioningLikeError,
    build_manifest,
    derive_public_key,
    format_public_key,
    read_private_seed,
)


#: One stylesheet for every page this tool serves — the form, the console and
#: the landing page — so moving between them never looks like switching tools.
#:
#: A design system, not page styles: spacing comes from one scale
#: (`--space-1` … `--space-8`, with `--gap` as the standard gap between blocks),
#: colours from tokens that have a light and a dark value, and every
#: interactive thing has the same radius, height and focus ring. Logical
#: properties (`inline-start`, `margin-inline`) are used throughout so the same
#: rules lay out correctly right-to-left (Persian) and left-to-right (English).
_STYLE_TEMPLATE = """
  __FONT_FACE__
  :root {
    --bg: #f4f6fb; --surface: #ffffff; --surface-2: #eef1f8; --surface-3: #e4e9f4;
    --border: #d9dfec; --border-strong: #c3ccdf;
    --text: #151a2d; --text-muted: #5b6684; --text-faint: #8a93ad;
    --primary: #2563eb; --primary-hover: #1d4fd8; --primary-soft: rgba(37,99,235,.10); --on-primary: #ffffff;
    --danger: #d83a4a; --danger-bg: #fdecee; --danger-border: #f3b7be;
    --success: #1f9d57; --success-bg: #e8f7ef; --success-border: #a9dcc0;
    --warn: #b7791f; --warn-bg: #fff6e0; --warn-border: #ecd391;
    --shadow: 0 1px 2px rgba(20,28,60,.06), 0 8px 24px rgba(20,28,60,.06);
    --radius: .85rem; --radius-sm: .55rem; --control-h: 2.75rem;
    --space-1: .25rem; --space-2: .5rem; --space-3: .75rem; --space-4: 1rem;
    --space-5: 1.5rem; --space-6: 2rem; --space-7: 3rem; --space-8: 4rem;
    --gap: var(--space-5);
    color-scheme: light;
  }
  :root[data-theme="dark"] {
    --bg: #0e1118; --surface: #161a24; --surface-2: #1c2130; --surface-3: #252b3d;
    --border: #2a3144; --border-strong: #3a4360;
    --text: #e9ecf5; --text-muted: #a0a9c2; --text-faint: #6f7a99;
    --primary: #4c8dff; --primary-hover: #6aa0ff; --primary-soft: rgba(76,141,255,.14); --on-primary: #08101f;
    --danger: #ff6b78; --danger-bg: #2c1519; --danger-border: #5e2a31;
    --success: #43c37c; --success-bg: #11291c; --success-border: #25583a;
    --warn: #e6b04f; --warn-bg: #2b2210; --warn-border: #5b4719;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 12px 32px rgba(0,0,0,.35);
    color-scheme: dark;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #0e1118; --surface: #161a24; --surface-2: #1c2130; --surface-3: #252b3d;
      --border: #2a3144; --border-strong: #3a4360;
      --text: #e9ecf5; --text-muted: #a0a9c2; --text-faint: #6f7a99;
      --primary: #4c8dff; --primary-hover: #6aa0ff; --primary-soft: rgba(76,141,255,.14); --on-primary: #08101f;
      --danger: #ff6b78; --danger-bg: #2c1519; --danger-border: #5e2a31;
      --success: #43c37c; --success-bg: #11291c; --success-border: #25583a;
      --warn: #e6b04f; --warn-bg: #2b2210; --warn-border: #5b4719;
      --shadow: 0 1px 2px rgba(0,0,0,.4), 0 12px 32px rgba(0,0,0,.35);
      color-scheme: dark;
    }
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    font-family: "IRANSansWeb", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    margin: 0; background: var(--bg); color: var(--text); line-height: 1.8; font-size: 15px;
    -webkit-font-smoothing: antialiased;
  }
  /* IRANSansWeb draws Latin digits as Persian ones; English pages use a Latin
     face so «38» reads as 38. Persian pages keep the product typeface. */
  html[lang="en"] body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  :focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
  h1 { font-size: 1.75rem; line-height: 1.4; margin: 0 0 var(--space-2); letter-spacing: -.01em; }
  h2 { font-size: 1.15rem; line-height: 1.5; margin: 0 0 var(--space-2); }
  h3 { font-size: 1rem; margin: 0 0 var(--space-2); }
  p { margin: var(--space-3) 0; }
  a { color: var(--primary); }
  small { color: var(--text-muted); font-size: .86rem; }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

  /* --- the top bar: brand, navigation, language, theme ------------------ */
  .topbar {
    position: sticky; top: 0; z-index: 20; background: color-mix(in srgb, var(--surface) 88%, transparent);
    backdrop-filter: blur(10px); border-bottom: 1px solid var(--border);
  }
  .topbar-inner {
    max-width: 78rem; margin-inline: auto; padding: var(--space-3) var(--space-5);
    display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-3) var(--space-5);
  }
  .brand { display: inline-flex; align-items: center; gap: var(--space-3); font-weight: 700; font-size: 1.05rem; color: var(--text); text-decoration: none; }
  .brand-mark {
    width: 2.1rem; height: 2.1rem; border-radius: .65rem; display: grid; place-items: center;
    background: linear-gradient(135deg, #2563eb, #7c3aed); color: #fff; font-size: 1.1rem;
  }
  .nav { display: flex; flex-wrap: wrap; gap: var(--space-1); }
  .nav a {
    padding: var(--space-2) var(--space-4); border-radius: var(--radius-sm); text-decoration: none;
    color: var(--text-muted); font-weight: 500; font-size: .93rem;
  }
  .nav a:hover { background: var(--surface-2); color: var(--text); }
  .nav a[aria-current="page"] { background: var(--primary-soft); color: var(--primary); }
  .topbar-tools { margin-inline-start: auto; display: flex; align-items: center; gap: var(--space-3); }
  .segmented { display: inline-flex; padding: var(--space-1); background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); gap: var(--space-1); }
  .segmented a, .segmented span {
    padding: var(--space-1) var(--space-3); border-radius: calc(var(--radius-sm) - 3px); font-size: .85rem;
    text-decoration: none; color: var(--text-muted); line-height: 1.7;
  }
  .segmented span.current { background: var(--surface); color: var(--text); box-shadow: 0 1px 2px rgba(0,0,0,.12); font-weight: 600; }
  .icon-button {
    width: var(--control-h); height: var(--control-h); border-radius: var(--radius-sm); border: 1px solid var(--border);
    background: var(--surface-2); color: var(--text); cursor: pointer; font-size: 1.05rem; padding: 0;
  }
  .icon-button:hover { background: var(--surface-3); }

  /* --- page frame ------------------------------------------------------- */
  .page { max-width: 78rem; margin-inline: auto; padding: var(--space-6) var(--space-5) var(--space-8); }
  .page-head { margin-bottom: var(--space-6); }
  .page-head p { color: var(--text-muted); margin: 0; max-width: 46rem; }
  .layout { display: grid; grid-template-columns: minmax(0, 1fr) 19rem; gap: var(--space-6); align-items: start; }
  @media (max-width: 62rem) { .layout { grid-template-columns: minmax(0, 1fr); } }
  .stack { display: flex; flex-direction: column; gap: var(--gap); }
  .aside { position: sticky; top: 5.5rem; display: flex; flex-direction: column; gap: var(--space-4); }
  @media (max-width: 62rem) { .aside { position: static; } }

  /* --- cards and notices ------------------------------------------------ */
  .card, fieldset {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: var(--space-5); margin: 0; box-shadow: var(--shadow); min-width: 0;
  }
  .card-title { display: block; font-weight: 700; font-size: 1.05rem; margin-bottom: var(--space-4); }
  /* A legend is laid out as a notch in its fieldset's border unless it floats;
     floating it full width makes it an ordinary heading inside the card. */
  fieldset > legend { float: inline-start; width: 100%; padding: 0; font-weight: 700; font-size: 1.05rem; margin-bottom: var(--space-4); }
  fieldset > legend + * { clear: both; }
  .card-lead { color: var(--text-muted); margin: calc(var(--space-2) * -1) 0 var(--space-4); font-size: .92rem; }
  .warning, .notice, .preview-live, .result-ok, .result-error {
    border-radius: var(--radius); padding: var(--space-4) var(--space-5); margin: 0; line-height: 1.85; border: 1px solid;
  }
  .warning { background: var(--warn-bg); border-color: var(--warn-border); }
  .notice { background: var(--surface-2); border-color: var(--border); }
  .preview-live { background: var(--success-bg); border-color: var(--success-border); }
  .result-ok { background: var(--success-bg); border-color: var(--success-border); margin-top: var(--gap); }
  .result-error { background: var(--danger-bg); border-color: var(--danger-border); margin-top: var(--gap); }
  .result-ok > *:first-child, .result-error > *:first-child { margin-top: 0; }

  /* --- fields ------------------------------------------------------------ */
  .fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); gap: var(--space-4) var(--space-5); }
  .fields .wide { grid-column: 1 / -1; }
  label { display: block; font-size: .92rem; font-weight: 500; }
  label > input[type=text], label > select, label > textarea, label > .hint-after { margin-top: var(--space-2); }
  input[type=text], select, textarea {
    width: 100%; min-height: var(--control-h); padding: var(--space-2) var(--space-4); background: var(--surface-2); color: var(--text);
    border: 1px solid var(--border); border-radius: var(--radius-sm); font: inherit; font-size: .95rem; font-weight: 400;
    transition: border-color .15s ease, box-shadow .15s ease;
  }
  textarea { padding-block: var(--space-3); }
  input[type=text]:hover, select:hover, textarea:hover { border-color: var(--border-strong); }
  input[type=text]:focus, select:focus, textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-soft); }
  input::placeholder { color: var(--text-faint); }
  .hint { display: block; margin-top: var(--space-2); color: var(--text-muted); font-size: .84rem; font-weight: 400; }
  .check { display: flex; gap: var(--space-3); align-items: flex-start; font-weight: 400; }
  .check input { margin-top: .4rem; }

  /* --- buttons ------------------------------------------------------------ */
  button, a.button {
    display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); min-height: var(--control-h);
    background: var(--primary); color: var(--on-primary); border: 1px solid transparent; border-radius: var(--radius-sm);
    padding: 0 var(--space-5); font: inherit; font-size: .95rem; font-weight: 600; cursor: pointer; text-decoration: none;
    transition: background .15s ease, transform .05s ease;
  }
  button:hover, a.button:hover { background: var(--primary-hover); }
  button:active { transform: translateY(1px); }
  button.secondary { background: var(--surface-2); color: var(--text); border-color: var(--border); }
  button.secondary:hover { background: var(--surface-3); }
  button.danger { background: var(--danger); color: #fff; }
  button.danger:hover { filter: brightness(1.08); }
  button.small { min-height: 2.15rem; padding: 0 var(--space-4); font-size: .85rem; font-weight: 500; }
  button.wide { width: 100%; }
  button.copy { min-height: 1.9rem; padding: 0 var(--space-3); font-size: .8rem; font-weight: 500; margin-inline-start: var(--space-2); }
  button.copy.is-copied { background: var(--success); color: #fff; }
  a.download { margin-top: var(--space-3); margin-inline-end: var(--space-3); }
  .actions { display: flex; flex-wrap: wrap; gap: var(--space-3); margin-top: var(--space-4); }

  code, pre {
    direction: ltr; text-align: left; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm);
    font-family: "Cascadia Code", "SF Mono", Consolas, "Courier New", monospace; font-size: .84rem; unicode-bidi: plaintext;
  }
  pre { display: block; padding: var(--space-3) var(--space-4); overflow-x: auto; margin: var(--space-3) 0; }
  code { display: inline-block; padding: 0 var(--space-2); }

  /* --- the feature picker ---------------------------------------------- */
  .picker-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-3); margin-bottom: var(--space-5); }
  .picker-toolbar .search { flex: 1 1 14rem; min-width: 12rem; }
  .chip {
    display: inline-flex; align-items: center; gap: var(--space-1); padding: 0 var(--space-3); min-height: 1.7rem;
    border-radius: 999px; background: var(--primary-soft); color: var(--primary); font-size: .8rem; font-weight: 600;
  }
  .chip.muted { background: var(--surface-2); color: var(--text-muted); font-weight: 500; }
  .chip.warn { background: var(--warn-bg); color: var(--warn); }
  .toggle { display: inline-flex; align-items: center; gap: var(--space-2); font-weight: 400; font-size: .88rem; color: var(--text-muted); }
  .feature-group { margin-bottom: var(--space-6); }
  .feature-group:last-child { margin-bottom: 0; }
  .group-head { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-3); }
  .group-head h3 { margin: 0; font-size: 1rem; }
  .group-head .group-actions { margin-inline-start: auto; display: flex; gap: var(--space-2); }
  /* A grid, not CSS `columns`: each card is several lines tall and a column
     break inside one would land between a feature and its own page list.
     `auto-fill` reflows to one column on a narrow window. */
  ul.feature-list {
    list-style: none; padding: 0; margin: 0; display: grid;
    grid-template-columns: repeat(auto-fill, minmax(19rem, 1fr)); gap: var(--space-3);
  }
  ul.feature-list li { margin: 0; min-width: 0; }
  ul.feature-list label.feature-card {
    display: flex; align-items: flex-start; gap: var(--space-3); height: 100%; padding: var(--space-4); cursor: pointer;
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); font-weight: 400;
    transition: border-color .15s ease, background .15s ease, box-shadow .15s ease;
  }
  ul.feature-list label.feature-card:hover { border-color: var(--border-strong); background: var(--surface-2); }
  ul.feature-list label.feature-card:has(input:checked) { border-color: var(--primary); background: var(--primary-soft); }
  ul.feature-list input { margin-top: .35rem; flex: 0 0 auto; width: 1.1rem; height: 1.1rem; accent-color: var(--primary); }
  .feature-text { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
  .feature-head { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
  .feature-name { font-weight: 600; }
  .feature-desc { color: var(--text-muted); line-height: 1.65; }
  .feature-key { display: inline-block; direction: ltr; unicode-bidi: plaintext; color: var(--text-faint); font-family: "Cascadia Code", Consolas, monospace; font-size: .78rem; }
  .feature-needs, .feature-pages { color: var(--text-muted); line-height: 1.6; }
  .feature-pages { color: var(--text-faint); }
  .no-match { text-align: center; color: var(--text-muted); padding: var(--space-6) 0; }
  [hidden] { display: none !important; }

  /* --- the summary column ------------------------------------------------ */
  .summary-count { font-size: 2.2rem; font-weight: 800; line-height: 1.2; }
  .summary-count small { font-size: .9rem; font-weight: 400; }
  .progress { height: .45rem; border-radius: 999px; background: var(--surface-3); overflow: hidden; margin: var(--space-3) 0; }
  .progress > span { display: block; height: 100%; width: 0; background: linear-gradient(90deg, #2563eb, #7c3aed); transition: width .2s ease; }

  /* --- landing, tables ---------------------------------------------------- */
  .option-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); gap: var(--gap); margin: var(--space-6) 0; }
  .option-card {
    display: flex; flex-direction: column; gap: var(--space-2); background: var(--surface); border: 1px solid var(--border);
    border-radius: calc(var(--radius) + .15rem); padding: var(--space-6); text-decoration: none; color: var(--text);
    box-shadow: var(--shadow); transition: border-color .15s ease, transform .15s ease;
  }
  .option-card:hover { border-color: var(--primary); transform: translateY(-2px); }
  .option-card .option-icon { font-size: 2rem; width: 3.4rem; height: 3.4rem; border-radius: var(--radius); display: grid; place-items: center; background: var(--primary-soft); margin-bottom: var(--space-3); }
  .option-card h2 { margin: 0; }
  .option-card p { color: var(--text-muted); font-size: .92rem; margin: 0; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); gap: var(--space-4); }
  .stat { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--space-4) var(--space-5); }
  .stat strong { display: block; font-size: 1.6rem; line-height: 1.3; }
  .stat span { color: var(--text-muted); font-size: .86rem; }
  .table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: start; padding: var(--space-3) var(--space-4); border-bottom: 1px solid var(--border); white-space: nowrap; }
  tbody tr:last-child td { border-bottom: 0; }
  tbody tr:hover { background: var(--surface-2); }
  th { color: var(--text-muted); font-weight: 600; font-size: .82rem; background: var(--surface-2); }
  .empty { text-align: center; padding: var(--space-7) var(--space-5); color: var(--text-muted); }
  .empty .option-icon { font-size: 2.2rem; margin-bottom: var(--space-3); }
"""

_FONT_FACE = (
    '@font-face { font-family: "IRANSansWeb"; '
    + (f'src: url("data:font/woff2;base64,{_IRANSANS_WOFF2_BASE64}") format("woff2"); ' if _IRANSANS_WOFF2_BASE64 else "")
    + "font-weight: normal; font-display: swap; }"
)
_STYLE = _STYLE_TEMPLATE.replace("__FONT_FACE__", _FONT_FACE)


# --- shared helpers --------------------------------------------------------


def _with_lang(path, lang):
    """A form action or link that keeps the language the operator chose.

    Persian is the default and is left off the URL, so every address a
    Persian-language operator already knows stays exactly as it was.
    """
    if lang == DEFAULT_LANGUAGE:
        return path
    return f"{path}{'&' if '?' in path else '?'}lang={lang}"


def _profile_datalist_html():
    """Suggestions for the free-text profile id field, not a closed set.

    `profile_id` stopped being an enum the running application enforces
    (2026-09-05 — see the comment above `PROFILES` in
    `common/deployment/registry.py`): a manifest naming a profile id this
    release has never seen is accepted as long as it is well-formed and the
    signature verifies, which is what makes onboarding a real new customer
    possible from this console with no code change. `PROFILES` still names
    the ids already in real use, so this `<datalist>` offers them as
    one-click suggestions — typing anything else is equally valid.
    """
    return "\n".join(
        f'<option value="{html.escape(pid)}">{html.escape(pid)} — {html.escape(description)}</option>'
        for pid, description in sorted(PROFILES.items())
    )


#: Which panel pages each feature turns on, derived from the real route
#: table (`common.deployment.pages`) rather than written down here. Resolved
#: once per process: it walks the URL resolver, and the answer cannot change
#: while the console is running.
_FEATURE_PAGES = None


def _feature_pages():
    """`feature -> page titles`, reading the panel's own routes.

    This console is a standalone script, so Django is not configured when it
    starts — and the route table is a Django thing. `config.settings`
    imports with no environment at all (every value it needs has a default),
    so setting it up here costs nothing and needs no settings module of this
    tool's own. Nothing is connected to: reading `urlpatterns` touches no
    database.

    A failure falls back to an empty mapping rather than taking the console
    down with it. The checklist then shows what it always showed — the
    feature keys and their dependencies — and loses only the page names,
    which is a degraded console rather than no console.
    """
    global _FEATURE_PAGES
    if _FEATURE_PAGES is None:
        try:
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
            import django

            django.setup()
            _FEATURE_PAGES = feature_page_titles()
        except (ImportError, RuntimeError) as error:
            # A checkout whose Django is not installed or whose settings
            # cannot be imported. Narrow on purpose: a bare `except
            # Exception` here hid a NameError during development and the
            # console silently showed every feature as opening no pages.
            print(f"[console] page list unavailable: {error}", file=sys.stderr)
            _FEATURE_PAGES = {}
    return _FEATURE_PAGES


def _document_attrs(lang):
    """`lang`/`dir` for the page's own `<html>`.

    English is left-to-right; the console's Persian is not. Both are set
    from one place so a page cannot be labelled English and laid out RTL.
    """
    return 'lang="en" dir="ltr"' if lang == "en" else 'lang="fa" dir="rtl"'


def _language_bar_html(lang, path):
    """The two language links, pointing back at the page they are on.

    Carried in the URL rather than a cookie or a session: this tool is a
    handful of stateless GETs served to one operator on 127.0.0.1, and a
    link that says which language it goes to is something they can bookmark
    or send to a colleague.
    """
    links = []
    for code, label in LANGUAGES:
        if code == lang:
            links.append(f'<span class="current" aria-current="true">{html.escape(label)}</span>')
        else:
            links.append(
                f'<a class="lang" lang="{code}" href="{html.escape(path)}?lang={code}">{html.escape(label)}</a>'
            )
    return (
        f'<div class="segmented lang-bar" role="group" aria-label="{html.escape(T(lang, "language"))}">'
        + "".join(links)
        + "</div>"
    )


def _feature_checkboxes_html(checked_features, lang="fa"):
    """The whole feature picker: a toolbar and every feature, grouped.

    Each card says what the feature is, its key (the identifier that goes
    into the signed manifest — never translated), what it needs, and which
    panel pages it opens. The pages are the product owner's request of
    2026-09-20 — «همهٔ صفحات و گزینه‌های پنل به‌صورت چک‌باکس در دسترس باشند و
    با منبع واقعی فیچرها همگام باشند (نه یک لیست دستیِ قدیمی)» — derived from
    the routes and their views' own `required_feature`, so a page added to the
    panel shows up here without anybody remembering to add it. The names,
    descriptions and groups come from `console_strings.FEATURE_META`, which a
    test holds equal to the registry.
    """
    checked = set(checked_features)
    pages = _feature_pages()
    needs = T(lang, "requires")
    opens = T(lang, "opens")
    off = T(lang, "off_by_default")
    by_group = {key: [] for key in FEATURE_GROUPS}
    for name, requires in sorted(FEATURE_DEPENDENCIES.items()):
        meta = FEATURE_META.get(name)
        group, fa_name, en_name, fa_desc, en_desc = meta if meta else ("platform", name, name, "", "")
        title = en_name if lang == "en" else fa_name
        description = en_desc if lang == "en" else fa_desc
        titles = pages.get(name, [])
        search = " ".join([name, fa_name, en_name, fa_desc, en_desc, " ".join(titles)]).lower()
        by_group.setdefault(group, []).append(
            f'<li data-search="{html.escape(search)}"><label class="feature-card">'
            f'<input type="checkbox" name="feature" value="{html.escape(name)}"'
            f'{" checked" if name in checked else ""} data-requires="{html.escape(",".join(sorted(requires)))}"'
            f' data-group="{html.escape(group)}">'
            f'<span class="feature-text">'
            f'<span class="feature-head"><span class="feature-name">{html.escape(title)}</span>'
            + (f'<span class="chip warn">{html.escape(off)}</span>' if name in DEFAULT_OFF_FEATURES else "")
            + f'</span><span class="feature-key">{html.escape(name)}</span>'
            + (f'<small class="feature-desc">{html.escape(description)}</small>' if description else "")
            + (
                f'<small class="feature-needs">{needs}: {html.escape(", ".join(sorted(requires)))}</small>'
                if requires else ""
            )
            + (
                f'<small class="feature-pages">{opens}: {html.escape("، ".join(titles))}</small>'
                if titles
                else f'<small class="feature-pages">{html.escape(T(lang, "no_pages"))}</small>'
            )
            + "</span></label></li>"
        )
    sections = []
    for key, (fa_title, en_title) in FEATURE_GROUPS.items():
        rows = by_group.get(key)
        if not rows:
            continue
        sections.append(
            f'<section class="feature-group" data-group="{html.escape(key)}">'
            f'<div class="group-head"><h3>{html.escape(en_title if lang == "en" else fa_title)}</h3>'
            f'<span class="chip muted" data-group-count></span>'
            f'<div class="group-actions">'
            f'<button type="button" class="secondary small" data-group-select="all">{html.escape(T(lang, "select_all"))}</button>'
            f'<button type="button" class="secondary small" data-group-select="none">{html.escape(T(lang, "select_none"))}</button>'
            f"</div></div>"
            f'<ul class="feature-list">{"".join(rows)}</ul></section>'
        )
    toolbar = (
        '<div class="picker-toolbar">'
        f'<label class="search sr-only-label"><span class="sr-only">{html.escape(T(lang, "search_features"))}</span>'
        f'<input type="text" id="feature-search" placeholder="{html.escape(T(lang, "search_features"))}" autocomplete="off"></label>'
        f'<span class="chip" id="feature-total"></span>'
        f'<label class="toggle"><input type="checkbox" id="only-selected"> {html.escape(T(lang, "only_selected"))}</label>'
        f'<button type="button" class="secondary small" data-feature-select="all">{html.escape(T(lang, "select_all"))}</button>'
        f'<button type="button" class="secondary small" data-feature-select="none">{html.escape(T(lang, "select_none"))}</button>'
        "</div>"
    )
    return (
        f'{toolbar}<div id="feature-list" class="feature-groups">{"".join(sections)}</div>'
        f'<p class="no-match" id="feature-empty" hidden>{html.escape(T(lang, "no_match"))}</p>'
    )


#: The client-side behaviour shared by every page: the feature picker
#: (dependency auto-check, dependents un-check, search, selected-only filter,
#: counters, select all/none per group and overall), the theme toggle and the
#: copy buttons. One script rather than a copy per page, so the form and the
#: console cannot drift apart.
_PAGE_SCRIPT = """
(() => {
  const root = document.documentElement;
  const saved = (() => { try { return localStorage.getItem("dolphin-console-theme"); } catch (e) { return null; } })();
  if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);
  const toggle = document.getElementById("theme-toggle");
  if (toggle) toggle.addEventListener("click", () => {
    const dark = root.getAttribute("data-theme") === "dark" ||
      (!root.getAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
    const next = dark ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("dolphin-console-theme", next); } catch (e) { /* the choice just is not remembered */ }
  });

  const list = document.getElementById("feature-list");
  if (list) {
    const boxes = () => Array.from(list.querySelectorAll('input[name="feature"]'));
    const find = (name) => list.querySelector('input[name="feature"][value="' + CSS.escape(name) + '"]');
    const search = document.getElementById("feature-search");
    const only = document.getElementById("only-selected");
    const total = document.getElementById("feature-total");
    const empty = document.getElementById("feature-empty");
    const summary = document.getElementById("summary-count");
    const bar = document.getElementById("summary-bar");
    const refresh = () => {
      const all = boxes();
      const picked = all.filter((box) => box.checked).length;
      if (total) total.textContent = picked + " / " + all.length + " " + ((document.getElementById("picker") || {dataset: {}}).dataset.totalLabel || "");
      if (summary) summary.firstChild.textContent = picked + " ";
      if (bar) bar.style.width = (all.length ? (picked * 100) / all.length : 0) + "%";
      const query = (search ? search.value : "").trim().toLowerCase();
      let visible = 0;
      list.querySelectorAll(".feature-group").forEach((group) => {
        const inGroup = Array.from(group.querySelectorAll("li"));
        let shown = 0;
        inGroup.forEach((item) => {
          const box = item.querySelector("input");
          const match = (!query || item.dataset.search.includes(query)) && (!only || !only.checked || box.checked);
          item.hidden = !match;
          if (match) shown += 1;
        });
        group.hidden = shown === 0;
        visible += shown;
        const count = group.querySelector("[data-group-count]");
        if (count) count.textContent = inGroup.filter((item) => item.querySelector("input").checked).length + " / " + inGroup.length;
      });
      if (empty) empty.hidden = visible !== 0;
    };
    list.addEventListener("change", (event) => {
      const box = event.target;
      if (!(box instanceof HTMLInputElement) || box.name !== "feature") return;
      if (box.checked) {
        (box.dataset.requires || "").split(",").filter(Boolean).forEach((name) => {
          const dependency = find(name);
          if (dependency && !dependency.checked) { dependency.checked = true; dependency.dispatchEvent(new Event("change", {bubbles: true})); }
        });
      } else {
        boxes().forEach((other) => {
          if (other.checked && (other.dataset.requires || "").split(",").includes(box.value)) {
            other.checked = false;
            other.dispatchEvent(new Event("change", {bubbles: true}));
          }
        });
      }
      refresh();
    });
    if (search) search.addEventListener("input", refresh);
    if (only) only.addEventListener("change", refresh);
    document.querySelectorAll("[data-feature-select]").forEach((button) => {
      button.addEventListener("click", () => {
        const on = button.dataset.featureSelect === "all";
        boxes().forEach((box) => { box.checked = on; });
        refresh();
      });
    });
    list.querySelectorAll("[data-group-select]").forEach((button) => {
      button.addEventListener("click", () => {
        const on = button.dataset.groupSelect === "all";
        button.closest(".feature-group").querySelectorAll("li:not([hidden]) input").forEach((box) => {
          if (box.checked !== on) { box.checked = on; box.dispatchEvent(new Event("change", {bubbles: true})); }
        });
        refresh();
      });
    });
    refresh();
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-copy]");
    if (!button) return;
    const original = button.textContent;
    const flash = (label, ok) => {
      button.textContent = label;
      button.classList.toggle("is-copied", ok);
      setTimeout(() => { button.textContent = original; button.classList.remove("is-copied"); }, 1500);
    };
    navigator.clipboard.writeText(button.dataset.copy).then(
      () => flash(button.dataset.done || "OK", true),
      // Denied permission or no secure context: the value is still right
      // there in the neighbouring <code>, so this only says "do it yourself".
      () => flash(button.dataset.fail || "!", false),
    );
  });
})();
"""


def _download_script(element_id, hex_payload, mime):
    """Turn a hex payload into a downloadable blob for one link.

    The payload travels inside the page (never over a second request), is
    decoded in the browser and is never written to this machine's disk.
    """
    return (
        "<script>(() => {"
        f'const hex = "{hex_payload}";'
        "const bytes = new Uint8Array(hex.match(/.{2}/g).map((pair) => parseInt(pair, 16)));"
        f'const url = URL.createObjectURL(new Blob([bytes], {{type: "{mime}"}}));'
        f'document.getElementById("{element_id}").href = url;'
        "})();</script>"
    )


def _preview_status_html(lang=DEFAULT_LANGUAGE):
    """A persistent banner, shown on every page load, naming whatever
    preview is currently running (if any) — so the operator never loses
    track of an open preview across other clicks in this tool, and always
    has the stop button and login details in front of them.
    """
    state = preview_runner.status()
    if state is None:
        return ""
    url = f"http://127.0.0.1:{state['port']}/"
    label = html.escape(state["display_name"]) if state["display_name"] else L(lang, "(بدون نام سفارشی)", "(no custom name)")
    feature_count = len(state["features"])
    done, fail = L(lang, "کپی شد", "Copied"), L(lang, "کپی نشد", "Copy failed")
    return f"""<div class="preview-live">
  <strong>{L(lang, "پیش‌نمایش زنده در حال اجراست", "A live preview is running")}</strong> — {label}, {feature_count} {L(lang, "فیچر", "features")}, {L(lang, "نسخهٔ", "profile")} {html.escape(state['profile_id'])}.
  <p><a href="{url}" target="_blank" rel="noopener">{L(lang, "باز کردن پیش‌نمایش", "Open the preview")} ↗</a></p>
  <p><small>{L(lang, "ورود پیش‌نمایش — نام کاربری:", "Preview sign-in — username:")} <code>{html.escape(state['username'])}</code>
     <button type="button" class="secondary copy" data-done="{done}" data-fail="{fail}" data-copy="{html.escape(state['username'])}">{L(lang, "کپی", "Copy")}</button>
     {L(lang, "گذرواژه:", "password:")} <code>{html.escape(state['password'])}</code>
     <button type="button" class="secondary copy" data-done="{done}" data-fail="{fail}" data-copy="{html.escape(state['password'])}">{L(lang, "کپی", "Copy")}</button>.
     {L(lang, "این ورود فقط برای همین پنجرهٔ موقت است و با توقف پیش‌نمایش از بین می‌رود.", "This sign-in belongs to this temporary window only and disappears when the preview stops.")}</small></p>
  <form method="post" action="{_with_lang('/preview/stop', lang)}">
    <button type="submit" class="danger small">{L(lang, "توقف پیش‌نمایش", "Stop the preview")}</button>
  </form>
</div>"""


def _shell(lang, *, title, path, body, active="", scripts=""):
    """Every page's `<html>`: top bar, language switch, theme toggle, content.

    One shell so the five pages cannot differ in how they frame their
    content; `active` marks the current section in the navigation.
    """

    def link(href, label, key):
        current = ' aria-current="page"' if active == key else ""
        return f'<a href="{_with_lang(href, lang)}"{current}>{html.escape(label)}</a>'

    return f"""<!doctype html>
<html {_document_attrs(lang)}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_STYLE}</style>
</head>
<body>
<header class="topbar"><div class="topbar-inner">
  <a class="brand" href="{_with_lang('/start/', lang)}"><span class="brand-mark" aria-hidden="true">🐬</span>{html.escape(T(lang, "brand"))}</a>
  <nav class="nav" aria-label="{L(lang, 'ناوبری', 'Navigation')}">
    {link('/start/', T(lang, 'home'), 'home')}
    {link('/', L(lang, 'ساخت Manifest', 'Build a manifest'), 'build')}
    {link('/console/', T(lang, 'deployments'), 'console')}
  </nav>
  <div class="topbar-tools">
    {_language_bar_html(lang, path)}
    <button type="button" class="icon-button" id="theme-toggle" aria-label="{L(lang, 'تغییر پوسته', 'Toggle theme')}" title="{L(lang, 'تغییر پوسته', 'Toggle theme')}">◐</button>
  </div>
</div></header>
<main class="page">
{body}
</main>
{scripts}
<script>{_PAGE_SCRIPT}</script>
</body>
</html>"""


def _page_head(title, lead=""):
    lead_html = f"<p>{html.escape(lead)}</p>" if lead else ""
    return f'<div class="page-head"><h1>{html.escape(title)}</h1>{lead_html}</div>'


def _landing_page(lang=DEFAULT_LANGUAGE):
    """`/start/` — what actually opens when the tool launches (`main()`
    points `webbrowser.open`/the desktop window here, not at `/`).

    Two cards, nothing else of its own: which of this tool's two real jobs
    the operator is here for. `/` (the quick manifest form) and `/console/`
    (everything recorded so far) already existed and already worked, so this
    adds a front door in front of them rather than folding either into the
    other. Below them, what this build can actually see.
    """
    pages = _feature_pages()
    stats = (
        f'<div class="stats">'
        f'<div class="stat"><strong>{len(FEATURE_DEPENDENCIES)}</strong><span>{L(lang, "قابلیت قابل انتخاب", "selectable features")}</span></div>'
        f'<div class="stat"><strong>{sum(len(titles) for titles in pages.values())}</strong><span>{L(lang, "صفحهٔ پنل پشت یک قابلیت", "panel pages behind a feature")}</span></div>'
        f'<div class="stat"><strong>{len(deployment_records.load_all())}</strong><span>{L(lang, "استقرار ثبت‌شده", "recorded deployments")}</span></div>'
        f"</div>"
    )
    body = f"""{_page_head(T(lang, "brand"), L(lang, "ساخت manifest امضاشده برای یک استقرار تازه، یا مدیریت استقرارهایی که قبلاً ثبت شده‌اند.", "Build a signed manifest for a new deployment, or manage the deployments already recorded."))}
<div class="option-grid">
  <a class="option-card" href="{_with_lang('/', lang)}">
    <div class="option-icon">➕</div>
    <h2>{L(lang, "ساخت جدید", "Build new")}</h2>
    <p>{L(lang, "فیچرهای یک مشتری تازه را تیک بزنید، پیش‌نمایش زنده بگیرید، و manifest/.env امضاشده بسازید.", "Tick a new customer's features, take a live preview, and build the signed manifest and .env.")}</p>
  </a>
  <a class="option-card" href="{_with_lang('/console/', lang)}">
    <div class="option-icon">📋</div>
    <h2>{L(lang, "مدیریت همهٔ استقرارها", "Manage all deployments")}</h2>
    <p>{L(lang, "فهرست هر استقراری که تاکنون از همین ماشین امضا شده — امضای تازه، ویرایش، یا حذف رکورد محلی.", "Every deployment signed from this machine so far — re-sign, edit, or remove the local record.")}</p>
  </a>
</div>
{stats}"""
    return _shell(lang, title=T(lang, "console_title"), path="/start/", body=body, active="home")


def _page(*, lang=DEFAULT_LANGUAGE, profile_id="", key_id="", private_key_path="", checked_features=(),
          deploy_slug="", deploy_host="", deploy_image="", deploy_manifest_path="/srv/dolphin/secrets/manifest.json",
          deploy_retention_days="0", preview_display_name="", result_html=""):
    """Render the whole page: warning banner, the form (repopulated with
    whatever was just submitted, so a mistake does not mean retyping
    everything), and a result section — success or error — from the last
    submission, if any.
    """
    profile_datalist = _profile_datalist_html()
    feature_picker = _feature_checkboxes_html(checked_features, lang)
    pattern_title = L(lang, "حروف کوچک لاتین/عدد/underscore/خط‌تیره، شروع با حرف، ۲ تا ۶۴ نویسه",
                      "Lowercase Latin letters, digits, underscore, hyphen; start with a letter; 2–64 characters")
    total_label = L(lang, "انتخاب‌شده", "selected")
    body = f"""{_page_head(L(lang, "ابزار ساخت Manifest امضاشده", "Signed manifest builder"), L(lang, "هویت استقرار، قابلیت‌ها و در صورت نیاز پیش‌نویس .env — همه در یک صفحه.", "The deployment identity, the features and, if you want it, a draft .env — on one page."))}
<div class="warning">
  <strong>{L(lang, "فقط برای مالک پلتفرم.", "Platform owner only.")}</strong> {L(lang, "این ابزار را فقط روی ماشینی اجرا کنید که کلید خصوصی امضا رویش نگه‌داری می‌شود — هرگز روی سرور مشتری. کلید خصوصی از مسیر فایل زیر خوانده می‌شود؛ هیچ‌جا لاگ، ذخیره یا نمایش داده نمی‌شود.", "Run this only on the machine that holds the private signing key — never on a customer server. The key is read from the file path below; it is never logged, stored or shown.")}
</div>
{_preview_status_html(lang)}
<form method="post" action="{_with_lang('/build', lang)}" class="layout" style="margin-top: var(--gap)">
  <div class="stack">
  <fieldset>
    <legend>{L(lang, "هویت manifest", "Manifest identity")}</legend>
    <div class="fields">
    <label>{L(lang, "شناسهٔ نسخه (profile)", "Profile id")}
      <input type="text" name="profile_id" list="profile-id-options" value="{html.escape(profile_id)}"
             placeholder="client-1" pattern="[a-z][a-z0-9_-]{{1,63}}"
             title="{html.escape(pattern_title)}" required dir="ltr">
      <datalist id="profile-id-options">{profile_datalist}</datalist>
      <span class="hint">{L(lang, "یکی از پیشنهادها را انتخاب کنید یا برای مشتری تازه یک شناسهٔ تازه تایپ کنید — دیگر به این سه محدود نیست.", "Pick a suggestion, or type a new id for a new customer — you are no longer limited to the existing ones.")}</span>
    </label>
    <label>{L(lang, "شناسهٔ کلید (key id)", "Key id")}
      <input type="text" name="key_id" value="{html.escape(key_id)}" placeholder="dolphin-2026" required dir="ltr">
    </label>
    <label class="wide">{L(lang, "مسیر فایل کلید خصوصی، روی همین ماشین", "Private key file path, on this machine")}
      <input type="text" name="private_key_path" value="{html.escape(private_key_path)}"
             placeholder="C:\\keys\\dolphin-manifest-signing.pem" required dir="ltr">
    </label>
    </div>
  </fieldset>
  <fieldset>
    <legend>{T(lang, "features_legend")}</legend>
    <p class="card-lead">{L(lang, "وابستگی‌های ناقص خودکار اضافه می‌شوند (هم همین‌جا موقع تیک‌زدن، هم دوباره، قطعی، سمت سرور موقع امضا) — دقیقاً همان قاعده‌ای که", "Missing dependencies are added automatically — here as you tick, and again, authoritatively, on the server when signing — by exactly the rule")} <code>scripts/new_deployment.py --print-resolved-features</code> {L(lang, "استفاده می‌کند.", "uses.")}</p>
    <div id="picker" data-total-label="{html.escape(total_label)}">{feature_picker}</div>
  </fieldset>
  <fieldset>
    <legend>{L(lang, "پیش‌نمایش زنده (اختیاری، بدون نیاز به کلید خصوصی)", "Live preview (optional, no private key needed)")}</legend>
    <p class="card-lead">{L(lang, "مشتری زنگ زده، اسم و ماژول‌های موردنظرش را گفته؟ فیچرهای بالا را تیک بزنید، اسمش را اینجا بنویسید و «پیش‌نمایش زنده» را بزنید — یک نمونهٔ واقعی و موقت از پنل، دقیقاً با همین فیچرها، روی یک پورت محلی دیگر بالا می‌آید تا پیش از هر تعهدی کامل چک‌اش کنید. این اسم فقط برای همین پیش‌نمایش است؛ نه در manifest/.env خروجی می‌رود و نه جایی ذخیره می‌شود — برند واقعی را خودِ مشتری، بعد از استقرار، از", "The customer called and named the modules they want? Tick the features above, type their name here and press «Live preview» — a real, temporary copy of the panel with exactly those features starts on another local port so you can check it fully before committing. The name is for this preview only; it goes into neither the manifest nor the .env and is stored nowhere — the customer sets the real brand themselves, after deployment, from")} <code>/branding/</code> {L(lang, "در پنل خودش تنظیم می‌کند.", "in their own panel.")}</p>
    <div class="fields">
    <label>{L(lang, "نام مشتری (فقط برای پیش‌نمایش)", "Customer name (preview only)")}
      <input type="text" name="preview_display_name" value="{html.escape(preview_display_name)}" placeholder="{L(lang, 'تیارا', 'Tiara')}">
    </label>
    </div>
    <div class="actions"><button type="submit" formaction="{_with_lang('/preview/start', lang)}" formnovalidate class="secondary">{T(lang, "preview")}</button></div>
  </fieldset>
  <fieldset>
    <legend>{L(lang, "پیش‌نویس .env (اختیاری — سطح ۲)", "Draft .env (optional — level 2)")}</legend>
    <p class="card-lead">{L(lang, "هردو فیلد «شناسهٔ استقرار» و «دامنه یا آی‌پی» را پر کنید تا کنار manifest، یک secrets/.env پیش‌نویس هم با رمزهای تصادفی تازه ساخته شود — دقیقاً همان چیزی که scripts/new_deployment.py می‌سازد. خالی بگذارید تا فقط manifest ساخته شود.", "Fill in both «Deployment slug» and «Domain or IP» to also get a draft secrets/.env with fresh random secrets next to the manifest — exactly what scripts/new_deployment.py builds. Leave them empty to build only the manifest.")}</p>
    <div class="fields">
    <label>{L(lang, "شناسهٔ استقرار (slug)", "Deployment slug")}
      <input type="text" name="deploy_slug" value="{html.escape(deploy_slug)}" placeholder="tiara" dir="ltr">
    </label>
    <label>{L(lang, "دامنه یا آی‌پی عمومی", "Public domain or IP")}
      <input type="text" name="deploy_host" value="{html.escape(deploy_host)}" placeholder="crm.tiara.ir" dir="ltr">
    </label>
    <label class="wide">{L(lang, "ایمیج اپلیکیشن (رفرنس reviewed، با digest)", "Application image (a reviewed reference, with digest)")}
      <input type="text" name="deploy_image" value="{html.escape(deploy_image)}"
             placeholder="ghcr.io/you/dolphin-app@sha256:..." dir="ltr">
    </label>
    <label>{L(lang, "مسیر manifest روی سرور مقصد", "Manifest path on the target server")}
      <input type="text" name="deploy_manifest_path" value="{html.escape(deploy_manifest_path)}" dir="ltr">
    </label>
    <label>{L(lang, "نگه‌داری بکاپ (روز، ۰ یعنی همیشه)", "Backup retention (days, 0 = keep forever)")}
      <input type="text" name="deploy_retention_days" value="{html.escape(deploy_retention_days)}" dir="ltr">
    </label>
    </div>
  </fieldset>
  {result_html}
  </div>
  <aside class="aside">
    <div class="card">
      <div class="card-title">{L(lang, "خلاصه", "Summary")}</div>
      <div class="summary-count" id="summary-count">0 <small>{L(lang, "قابلیت انتخاب شده", "features selected")}</small></div>
      <div class="progress" aria-hidden="true"><span id="summary-bar"></span></div>
      <p class="card-lead" style="margin: 0 0 var(--space-4)">{L(lang, "وابستگی‌ها خودکار کامل می‌شوند.", "Dependencies are completed automatically.")}</p>
      <button type="submit" class="wide">{L(lang, "ساخت و امضای Manifest", "Build and sign the manifest")}</button>
    </div>
  </aside>
</form>"""
    return _shell(lang, title=L(lang, "ابزار ساخت Manifest", "Manifest builder"), path="/", body=body, active="build")


def _deploy_steps_text(*, slug, host, image, manifest_keys_line, manifest_path, lang=DEFAULT_LANGUAGE):
    """The short, customer-specific cheat sheet bundled into the deployment
    zip — not a copy of the runbook (which stays the single source of truth
    and could drift from a duplicated copy), just this deployment's own
    values dropped into the one command `docs/ops/DOLPHIN_DEPLOYMENT_
    RUNBOOK.md` section 1.0 already documents as the one-command path.
    """
    if lang == "en":
        return f"""Deployment guide — {slug}
====================================

This bundle holds the signed manifest.json and a draft .env. The full guide:
docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md (section 1).

## Recommended — let the customer's own server generate the secrets (safest)

On the customer's server, from the root of a checkout of the Dolphin repository:

    sudo ./scripts/quickstart.sh --slug {slug} --host {host} \\
        --app-image {image} \\
        --manifest /path/to/manifest.json --manifest-keys '{manifest_keys_line}' \\
        --tls-cert /path/to/fullchain.pem --tls-key /path/to/privkey.pem

(Point --manifest at the manifest.json file in this bundle. If a real TLS
certificate is not ready yet, replace the two TLS flags with --self-signed-tls
— for testing only, never for the final deployment.)

## Second way — use the attached .env as it is

If you prefer the secrets generated on your laptop to fresh ones on the server,
copy this bundle's dolphin.env to secrets/.env on the server and continue with
section 1.16 of the guide — never both ways together.

The manifest path this .env assumes on the target server: {manifest_path}

## The manifest public key (for both ways, verbatim)

{manifest_keys_line}
"""
    return f"""راهنمای استقرار — {slug}
====================================

این بسته شامل manifest.json امضاشده و یک پیش‌نویس .env است. راهنمای کامل:
docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md (بخش ۱).

## راه پیشنهادی — رمزها روی خودِ سرور مشتری ساخته شوند (امن‌ترین حالت)

روی سرور مشتری، از ریشهٔ یک checkout از مخزن Dolphin:

    sudo ./scripts/quickstart.sh --slug {slug} --host {host} \\
        --app-image {image} \\
        --manifest /path/to/manifest.json --manifest-keys '{manifest_keys_line}' \\
        --tls-cert /path/to/fullchain.pem --tls-key /path/to/privkey.pem

(مسیر manifest.json را به فایل هم‌پیوستِ همین بسته اشاره دهید. اگر گواهی
TLS واقعی هنوز آماده نیست، دو فلگ TLS بالا را با --self-signed-tls
جایگزین کنید — فقط برای تست، نه استقرار نهایی.)

## راه دوم — همین .env پیوست را مستقیم استفاده کنید

اگر ترجیح می‌دهید به‌جای رمزهای تازهٔ سرور، همان dolphin.env این بسته
(رمزهای تولیدشده روی لپ‌تاپ شما) را به کار ببرید، آن را روی سرور در
secrets/.env کپی کنید و طبق بخش ۱.۱۶ راهنما ادامه دهید — نه هر دو راه را
با هم.

مسیر manifest روی سرور مقصد که در این .env فرض شده: {manifest_path}

## کلید عمومی manifest (برای هر دو راه، عیناً)

{manifest_keys_line}
"""


def _deployment_bundle_zip_hex(*, manifest_bytes, env_content, deploy_steps_text):
    """A single zip — manifest.json, dolphin.env (when there is one), and
    DEPLOY-STEPS.txt — built in memory, never written to this machine's own
    disk, hex-encoded the same way the individual downloads already are so
    the browser reconstructs it client-side without a second HTTP round trip.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest_bytes)
        if env_content is not None:
            archive.writestr("dolphin.env", env_content)
        archive.writestr("DEPLOY-STEPS.txt", deploy_steps_text)
    return buffer.getvalue().hex()


def _error_html(lang, headline_fa, headline_en, detail):
    return (
        f'<div class="result-error"><strong>{L(lang, headline_fa, headline_en)}</strong> {html.escape(str(detail))}</div>'
        if detail else f'<div class="result-error"><strong>{L(lang, headline_fa, headline_en)}</strong></div>'
    )


def _profile_error(lang):
    return L(
        lang,
        "شناسهٔ نسخه باید ۲ تا ۶۴ نویسه، حروف کوچک لاتین/عدد/underscore/خط‌تیره، و شروع‌شونده با حرف باشد — دیگر لازم نیست یکی از سه مقدار قبلی باشد.",
        "The profile id must be 2–64 characters: lowercase Latin letters, digits, underscore or hyphen, starting with a letter — it no longer has to be one of the three earlier values.",
    )


def _manifest_ok_block(lang, *, features, added, profile_id, public_key_line, manifest_bytes, fresh=False):
    """The success block for a signed manifest, shared by the build and the re-sign."""
    manifest_json = json.dumps(json.loads(manifest_bytes), ensure_ascii=False, indent=2)
    added_note = ""
    if added:
        added_list = ", ".join(
            f"{feature} ({L(lang, 'نیازمند', 'needs')} {', '.join(sorted(requires))})"
            for feature, requires in sorted(added.items())
        )
        added_note = f"<p>{L(lang, 'به‌خاطر وابستگی، این‌ها هم اضافه شدند:', 'Added because of dependencies:')} {html.escape(added_list)}</p>"
    feature_list = "، ".join(sorted(features)) if lang == "fa" else ", ".join(sorted(features))
    headline = (
        L(lang, "Manifest تازه ساخته و امضا شد", "A new manifest was built and signed")
        if fresh else L(lang, "Manifest ساخته و امضا شد", "The manifest was built and signed")
    )
    return f"""<div class="result-ok">
  <strong>{headline}</strong> — {len(features)} {L(lang, "فیچر", "features")}, {L(lang, "نسخهٔ", "profile")} {html.escape(profile_id)}.
  {added_note}
  <p>{L(lang, "فیچرهای نهاییِ امضاشده:", "Signed features:")} {html.escape(feature_list)}</p>
  <p>{L(lang, "کلید عمومی — این خط را عیناً در", "Public key — put this line verbatim in")} <code>DOLPHIN_DEPLOYMENT_MANIFEST_KEYS</code> {L(lang, "بگذارید:", ":")}</p>
  <pre>{html.escape(public_key_line)}</pre>
  <a class="button download" download="manifest.json" id="download-link" href="#">{L(lang, "دانلود manifest.json", "Download manifest.json")}</a>
  {_download_script("download-link", manifest_bytes.hex(), "application/json")}
  <p><small>{L(lang, "محتوای فایل:", "File contents:")}</small></p>
  <pre>{html.escape(manifest_json)}</pre>
</div>"""


def _build_result_html(form, lang=DEFAULT_LANGUAGE):
    """Try to build and sign a manifest from submitted form fields.

    Returns the HTML for the result section — success (with a download link
    and the public-key line) or a plain-language error — and never raises:
    every failure this can name (bad key file, unknown feature, an unmet
    dependency the server-side resolution still could not settle, an
    unwritable... nothing is written server-side at all) becomes a message
    in that HTML, not a stack trace in the browser.
    """
    profile_id = (form.get("profile_id", [""])[0] or "").strip()
    key_id = (form.get("key_id", [""])[0] or "").strip()
    private_key_path = (form.get("private_key_path", [""])[0] or "").strip()
    requested_features = set(form.get("feature", []))
    deploy_slug = (form.get("deploy_slug", [""])[0] or "").strip()
    deploy_host = (form.get("deploy_host", [""])[0] or "").strip()
    deploy_image = (form.get("deploy_image", [""])[0] or "").strip() or "dolphin-app:latest"
    deploy_manifest_path = (form.get("deploy_manifest_path", [""])[0] or "").strip() \
        or "/srv/dolphin/secrets/manifest.json"
    deploy_retention_days_raw = (form.get("deploy_retention_days", [""])[0] or "").strip() or "0"

    try:
        if not valid_profile_id(profile_id):
            raise ProvisioningError(_profile_error(lang))
        if not key_id:
            raise ProvisioningError(L(lang, "شناسهٔ کلید الزامی است.", "The key id is required."))
        if not private_key_path:
            raise ProvisioningError(L(lang, "مسیر فایل کلید خصوصی الزامی است.", "The private key file path is required."))
        if not requested_features:
            raise ProvisioningError(L(lang, "دست‌کم یک فیچر را تیک بزنید.", "Tick at least one feature."))

        # The .env fields are all-or-nothing: either both slug and host are
        # given and a full draft is generated, or neither is and this call
        # behaves exactly like Level 1 (manifest only). One filled in without
        # the other is treated as a mistake, not a partial request — a slug
        # with no host cannot become DJANGO_ALLOWED_HOSTS, and a host with no
        # slug cannot name a database.
        want_env = bool(deploy_slug or deploy_host)
        if want_env:
            if not deploy_slug or not deploy_host:
                raise ProvisioningError(L(
                    lang,
                    "برای پیش‌نویس .env هم «شناسهٔ استقرار» و هم «دامنه یا آی‌پی» لازم است.",
                    "A draft .env needs both the deployment slug and the domain or IP.",
                ))
            if not SLUG_PATTERN.match(deploy_slug) or deploy_slug.startswith("pg_"):
                raise ProvisioningError(L(
                    lang,
                    "شناسهٔ استقرار باید ۲ تا ۴۱ کاراکتر، حروف کوچک لاتین، شروع‌شونده با حرف باشد و نباید با pg_ شروع شود — نام دیتابیس و نقش‌های PostgreSQL از رویش ساخته می‌شود.",
                    "The deployment slug must be 2–41 characters, lowercase Latin letters, starting with a letter and not starting with pg_ — the database and PostgreSQL role names are built from it.",
                ))
            if not HOST_PATTERN.match(deploy_host):
                raise ProvisioningError(L(
                    lang,
                    "دامنه یا آی‌پی نامعتبر است — بدون scheme، پورت یا مسیر.",
                    "The domain or IP is not valid — no scheme, port or path.",
                ))
            try:
                deploy_retention_days = int(deploy_retention_days_raw)
                if deploy_retention_days < 0:
                    raise ValueError
            except ValueError as error:
                raise ProvisioningError(L(
                    lang, "نگه‌داری بکاپ باید یک عدد صحیح غیرمنفی باشد.",
                    "Backup retention must be a non-negative whole number.",
                )) from error

        features, added = resolve_features(requested_features)
        seed = read_private_seed(private_key_path)
        public_key = derive_public_key(seed)
        issued_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        manifest_bytes = build_manifest(
            seed=seed, key_id=key_id, profile_id=profile_id,
            features=sorted(features), issued_at=issued_at,
        )
    except (ProvisioningError, ProvisioningLikeError, ValueError, OSError) as error:
        return _error_html(lang, "ساخته نشد:", "Not built:", error)

    public_key_line = format_public_key(key_id, public_key)
    manifest_block = _manifest_ok_block(
        lang, features=features, added=added, profile_id=profile_id,
        public_key_line=public_key_line, manifest_bytes=manifest_bytes,
    )

    if not want_env:
        return manifest_block

    # Reuses new_deployment.env_lines verbatim — same secret generation
    # (secrets.token_urlsafe(48)), same ordering, same comments — so this
    # draft and the CLI tool can never quietly disagree about what a fresh
    # .env looks like. manifest_keys is the line just derived above, so the
    # draft already points at the manifest this same submission signed.
    env_content = "\n".join(env_lines(
        slug=deploy_slug, host=deploy_host, image=deploy_image, profile=profile_id,
        manifest_path=deploy_manifest_path, manifest_keys=public_key_line,
        retention_days=deploy_retention_days,
    ))
    env_hex = env_content.encode("utf-8").hex()

    # A slug names a real deployment, so this submission is worth
    # remembering — the console (`/console/`) is exactly this list. Purely
    # additive bookkeeping: it cannot fail the request that already
    # succeeded above, and a record store that cannot be written to (a
    # read-only checkout, a permissions problem) degrades to "this build
    # was not recorded", not to an error on a manifest that already signed
    # correctly.
    try:
        existing_record = deployment_records.get(deploy_slug)
        deployment_records.upsert(deployment_records.DeploymentRecord(
            slug=deploy_slug,
            display_name=existing_record.display_name if existing_record else "",
            host=deploy_host, profile_id=profile_id,
            features=tuple(sorted(features)), key_id=key_id, app_image=deploy_image,
            manifest_path=deploy_manifest_path, retention_days=deploy_retention_days,
            manifest_issued_at=issued_at,
            notes=existing_record.notes if existing_record else "",
        ))
        console_note = (
            f'<p><small>{L(lang, "در کنسول هم ثبت شد", "Also recorded in the console")}: '
            f'<a href="{_with_lang("/console/" + html.escape(deploy_slug) + "/", lang)}">{html.escape(deploy_slug)}</a></small></p>'
        )
    except deployment_records.DeploymentRecordError:
        console_note = (
            f'<p><small>{L(lang, "ثبت در کنسول ناموفق بود؛ خودِ manifest و .env بالا هنوز معتبرند.", "Recording in the console failed; the manifest and .env above are still valid.")}</small></p>'
        )

    deploy_steps_text = _deploy_steps_text(
        slug=deploy_slug, host=deploy_host, image=deploy_image,
        manifest_keys_line=public_key_line, manifest_path=deploy_manifest_path, lang=lang,
    )
    bundle_hex = _deployment_bundle_zip_hex(
        manifest_bytes=manifest_bytes, env_content=env_content, deploy_steps_text=deploy_steps_text,
    )

    env_block = f"""<div class="result-ok">
  <strong>{L(lang, "پیش‌نویس .env هم ساخته شد", "The draft .env was built too")}</strong> — {L(lang, "رمزهای تصادفی تازه، فقط همین یک بار نمایش داده می‌شوند (هیچ‌جای سرور این ابزار ذخیره نمی‌شوند).", "fresh random secrets, shown only this once (this tool stores them nowhere).")}
  <p><small>{L(lang, "پیش از استفادهٔ واقعی:", "Before real use:")} <code>DOLPHIN_APP_IMAGE</code> {L(lang, "و مسیرهای TLS را با مقادیر واقعی جایگزین کنید — این‌ها فقط پیش‌نویس‌اند.", "and the TLS paths must be replaced with real values — these are only drafts.")}</small></p>
  {console_note}
  <p>
    <a class="button download" download="dolphin-deploy-{html.escape(deploy_slug)}.zip" id="download-link-bundle" href="#">{L(lang, "دانلود بستهٔ استقرار (zip)", "Download the deployment bundle (zip)")}</a>
    <a class="button download secondary" download="dolphin.env" id="download-link-env" href="#">{L(lang, "دانلود .env (تکی)", "Download .env (alone)")}</a>
  </p>
  <p><small>{L(lang, "بسته: manifest.json + dolphin.env + راهنمای گام‌به‌گام، یک فایل برای کپی به سرور مشتری.", "The bundle: manifest.json + dolphin.env + a step-by-step guide, one file to carry to the customer's server.")}</small></p>
  {_download_script("download-link-bundle", bundle_hex, "application/zip")}
  {_download_script("download-link-env", env_hex, "text/plain")}
  <p><small>{L(lang, "محتوای فایل:", "File contents:")}</small></p>
  <pre>{html.escape(env_content)}</pre>
</div>"""
    return manifest_block + env_block


def _build_preview_result_html(form, lang=DEFAULT_LANGUAGE):
    """Start (or restart) the live preview from the ticked features and the
    optional customer name. No key required — `preview_runner.start` signs
    with a one-time in-memory key, never the operator's real one.

    Returns only an *error* block on failure; on success the persistent
    `_preview_status_html()` banner at the top of `_page()` already shows
    everything there is to show, so this returns nothing rather than saying
    the same thing twice.
    """
    profile_id = (form.get("profile_id", [""])[0] or "").strip()
    requested_features = set(form.get("feature", []))
    display_name = (form.get("preview_display_name", [""])[0] or "").strip()
    failed = ("پیش‌نمایش ساخته نشد:", "The preview was not built:")

    if not valid_profile_id(profile_id):
        return _error_html(lang, *failed, L(lang, "فرمت شناسهٔ نسخه نامعتبر است.", "The profile id format is not valid."))
    if not requested_features:
        return _error_html(lang, *failed, L(lang, "دست‌کم یک فیچر را تیک بزنید.", "Tick at least one feature."))

    # A typed name means "show me this with the customer's own brand" —
    # the same auto-completion spirit as a feature's own dependencies,
    # just one level up: a name with no custom_branding feature would
    # preview as plain Dolphin branding, which is not what typing a name
    # asked for.
    if display_name:
        requested_features = requested_features | {"custom_branding"}

    try:
        features, _added = resolve_features(requested_features)
    except ProvisioningError as error:
        return _error_html(lang, *failed, error)

    try:
        preview_runner.start(profile_id=profile_id, features=features, display_name=display_name)
    except preview_runner.PreviewError as error:
        return _error_html(lang, "پیش‌نمایش بالا نیامد:", "The preview did not start:", error)
    except Exception as error:  # noqa: BLE001 — a subprocess/OS failure here
        # must become a readable message, never a stack trace in the
        # browser (the same guarantee `_build_result_html` gives for
        # signing failures) — `preview_runner.start` already guarantees any
        # partially-started subprocess/temp directory was cleaned up before
        # this was raised.
        return _error_html(lang, "پیش‌نمایش بالا نیامد:", "The preview did not start:", error)
    return ""


def _build_reissue_result_html(record, form, lang=DEFAULT_LANGUAGE):
    """Sign a fresh manifest for an existing console record, and — only if
    asked for — a fresh `.env` draft alongside it. Mirrors
    `_build_result_html` closely (same validation order, same signing call),
    but starts from a stored record instead of a blank form, and always
    updates that record with what this actually just signed, so the console
    keeps reflecting the last thing handed to this customer.

    `.env` regeneration is opt-in (`regenerate_env` checkbox) rather than
    automatic like the create form's all-or-nothing slug+host rule: this
    record already has a slug and host, so every reissue could otherwise
    silently mint a fresh `.env` full of brand-new random secrets — which
    would stop matching whatever the customer's server is actually running
    until someone updates it there too. A manifest-only reissue (a feature
    flipped on, a profile changed) should not carry that side effect unless
    it is actually wanted.
    """
    key_id = (form.get("key_id", [""])[0] or "").strip()
    private_key_path = (form.get("private_key_path", [""])[0] or "").strip()
    profile_id = (form.get("profile_id", [""])[0] or "").strip()
    requested_features = set(form.get("feature", []))
    deploy_image = (form.get("deploy_image", [""])[0] or "").strip() or record.app_image or "dolphin-app:latest"
    regenerate_env = bool(form.get("regenerate_env", [""])[0])

    try:
        if not valid_profile_id(profile_id):
            raise ProvisioningError(_profile_error(lang))
        if not key_id:
            raise ProvisioningError(L(lang, "شناسهٔ کلید الزامی است.", "The key id is required."))
        if not private_key_path:
            raise ProvisioningError(L(lang, "مسیر فایل کلید خصوصی الزامی است.", "The private key file path is required."))
        if not requested_features:
            raise ProvisioningError(L(lang, "دست‌کم یک فیچر را تیک بزنید.", "Tick at least one feature."))

        features, added = resolve_features(requested_features)
        seed = read_private_seed(private_key_path)
        public_key = derive_public_key(seed)
        issued_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        manifest_bytes = build_manifest(
            seed=seed, key_id=key_id, profile_id=profile_id,
            features=sorted(features), issued_at=issued_at,
        )
    except (ProvisioningError, ProvisioningLikeError, ValueError, OSError) as error:
        return _error_html(lang, "ساخته نشد:", "Not built:", error)

    public_key_line = format_public_key(key_id, public_key)
    manifest_block = _manifest_ok_block(
        lang, features=features, added=added, profile_id=profile_id,
        public_key_line=public_key_line, manifest_bytes=manifest_bytes, fresh=True,
    )

    env_block = ""
    if regenerate_env:
        env_content = "\n".join(env_lines(
            slug=record.slug, host=record.host, image=deploy_image, profile=profile_id,
            manifest_path=record.manifest_path, manifest_keys=public_key_line,
            retention_days=record.retention_days,
        ))
        env_block = f"""<div class="result-ok">
  <strong>{L(lang, "پیش‌نویس .env تازه هم ساخته شد", "A fresh draft .env was built too")}</strong> — {L(lang, "رمزهای تصادفی تازه، فقط همین یک بار نمایش داده می‌شوند.", "fresh random secrets, shown only this once.")}
  <p><small>{L(lang, "این رمزها با آنچه سرور مشتری همین الان اجرا می‌کند فرق دارد — پیش از استفادهٔ واقعی، رمزهای دیتابیس/سرویس‌ها را روی خودِ سرور هم به‌روز کنید، وگرنه سرویس بالا نمی‌آید.", "These secrets differ from what the customer's server runs right now — update the database and service secrets on the server too before real use, or the service will not start.")}</small></p>
  <a class="button download" download="dolphin.env" id="download-link-env" href="#">{L(lang, "دانلود .env", "Download .env")}</a>
  {_download_script("download-link-env", env_content.encode("utf-8").hex(), "text/plain")}
  <p><small>{L(lang, "محتوای فایل:", "File contents:")}</small></p>
  <pre>{html.escape(env_content)}</pre>
</div>"""

    deployment_records.upsert(deployment_records.DeploymentRecord(
        slug=record.slug, display_name=record.display_name, host=record.host,
        profile_id=profile_id, features=tuple(sorted(features)), key_id=key_id,
        app_image=deploy_image, manifest_path=record.manifest_path,
        retention_days=record.retention_days, manifest_issued_at=issued_at,
        notes=record.notes,
    ))
    return manifest_block + env_block


def _decode_manifest_payload(raw_bytes):
    """Read a signed manifest's own public fields — key_id, profile_id,
    features, issued_at — with no signature check and no private key.

    Deliberately not `common.deployment.manifest.verify_manifest_bytes`:
    that function needs a trusted-public-key mapping this console has no
    concept of (it signs manifests, it does not verify them against a
    deployment's trust store), and verifying is not what importing is for —
    a manifest already sitting on disk, already handed to a customer, is
    already a fact; this only reads what it says, the same way a human
    would read the JSON by eye. `sign_deployment_manifest.py`'s own
    `build_manifest` already guaranteed the shape on the way out; this is
    that shape's inverse, not a new format.
    """
    envelope = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(envelope, dict):
        raise ValueError("پروندهٔ manifest باید یک شیء JSON باشد. / The manifest file must be a JSON object.")
    key_id = envelope.get("key_id")
    if not isinstance(key_id, str) or not key_id:
        raise ValueError("پروندهٔ manifest شناسهٔ کلید ندارد. / The manifest file has no key id.")
    payload_raw = envelope.get("payload")
    if not isinstance(payload_raw, str) or not payload_raw:
        raise ValueError("پروندهٔ manifest بخش payload ندارد. / The manifest file has no payload.")
    payload = json.loads(base64.b64decode(payload_raw, validate=True).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("محتوای payload باید یک شیء JSON باشد. / The payload must be a JSON object.")
    profile_id = payload.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id:
        raise ValueError("payload شناسهٔ نسخه (profile_id) ندارد. / The payload has no profile_id.")
    features = payload.get("features")
    if not isinstance(features, list) or not all(isinstance(item, str) for item in features):
        raise ValueError("فهرست فیچرهای payload نامعتبر است. / The payload feature list is not valid.")
    issued_at = payload.get("issued_at")
    if not isinstance(issued_at, str) or not issued_at:
        raise ValueError("payload زمان صدور (issued_at) ندارد. / The payload has no issued_at.")
    return {"key_id": key_id, "profile_id": profile_id, "features": features, "issued_at": issued_at}


def _build_import_result_html(form, lang=DEFAULT_LANGUAGE):
    """Bring an already-signed manifest into the local console archive as an
    editable record — no key, no re-signing, nothing sent anywhere.

    For a deployment first signed before this console existed (or signed by
    hand with `sign_deployment_manifest.py`), the archive has never heard of
    it: it does not appear at `/console/`, and there is nothing to click
    "امضای manifest تازه" on. This is the missing first step, not a new
    manifest — the slug this form is given is bookkeeping the operator
    supplies (a manifest carries no slug of its own), everything else comes
    from the file's own public payload.
    """
    slug = (form.get("import_slug", [""])[0] or "").strip()
    manifest_path = (form.get("import_manifest_path", [""])[0] or "").strip()
    display_name = (form.get("import_display_name", [""])[0] or "").strip()
    host = (form.get("import_host", [""])[0] or "").strip()
    failed = ("درون‌ریزی نشد:", "Not imported:")

    if not slug:
        return _error_html(lang, *failed, L(lang, "شناسهٔ استقرار الزامی است.", "The deployment slug is required."))
    if not manifest_path:
        return _error_html(lang, *failed, L(lang, "مسیر پروندهٔ manifest الزامی است.", "The manifest file path is required."))

    try:
        raw_bytes = Path(manifest_path).read_bytes()
        decoded = _decode_manifest_payload(raw_bytes)
        if not valid_profile_id(decoded["profile_id"]):
            raise ValueError(f"{L(lang, 'شناسهٔ نسخهٔ payload نامعتبر است:', 'The payload profile id is not valid:')} {decoded['profile_id']!r}")
        record = deployment_records.upsert(deployment_records.DeploymentRecord(
            slug=slug, display_name=display_name, host=host,
            profile_id=decoded["profile_id"], features=tuple(sorted(decoded["features"])),
            key_id=decoded["key_id"], manifest_issued_at=decoded["issued_at"],
        ))
    except OSError as error:
        return _error_html(lang, *failed, f"{L(lang, 'پرونده خوانده نشد:', 'The file could not be read:')} {error}")
    except (json.JSONDecodeError, binascii.Error, UnicodeDecodeError, ValueError) as error:
        return _error_html(lang, *failed, error)
    except deployment_records.DeploymentRecordError as error:
        return _error_html(lang, *failed, error)

    feature_list = ", ".join(sorted(record.features))
    return f"""<div class="result-ok">
  <strong>«{html.escape(slug)}» {L(lang, "به بایگانی کنسول اضافه شد", "was added to the console archive")}</strong> —
  {L(lang, "نسخهٔ", "profile")} {html.escape(record.profile_id)}, {len(record.features)} {L(lang, "فیچر", "features")}, {L(lang, "شناسهٔ کلید", "key id")} {html.escape(record.key_id)}.
  <p>{L(lang, "فیچرهای خوانده‌شده:", "Features read:")} {html.escape(feature_list)}</p>
  <p>{L(lang, "هیچ کلید خصوصی خوانده یا لمس نشد؛ چیزی دوباره امضا نشد — فقط payload عمومی پرونده خوانده شد.", "No private key was read or touched; nothing was re-signed — only the file's public payload was read.")}</p>
  <p><a href="{_with_lang("/console/" + html.escape(slug) + "/", lang)}">→ {L(lang, "رفتن به", "Go to")} «{html.escape(slug)}» {L(lang, "برای امضای مجدد یا ویرایش", "to re-sign or edit")}</a></p>
</div>"""


def _console_list_page(records, *, lang=DEFAULT_LANGUAGE, message="", import_result_html="",
                        import_slug="", import_manifest_path="", import_display_name="", import_host=""):
    """`/console/` — every deployment recorded so far, newest signature
    first. This is purely a read of `deployment_records.load_all()`; nothing
    here reaches any customer host.
    """
    message_html = f'<div class="notice">{html.escape(message)}</div>' if message else ""
    if not records:
        body_table = (
            f'<div class="card empty"><div class="option-icon">📭</div>'
            f'<p>{L(lang, "هنوز هیچ استقراری در کنسول ثبت نشده. برای ثبت اولین مورد،", "No deployment has been recorded in the console yet. To record the first one, fill in")} '
            f'<a href="{_with_lang("/", lang)}">{L(lang, "فرم ساخت manifest", "the manifest form")}</a> '
            f'{L(lang, "را با «شناسهٔ استقرار» و «دامنه یا آی‌پی» پر کنید.", "with a deployment slug and a domain or IP.")}</p></div>'
        )
    else:
        rows = "\n".join(
            f"""<tr>
              <td><a href="{_with_lang("/console/" + html.escape(record.slug) + "/", lang)}">{html.escape(record.display_name or record.slug)}</a></td>
              <td dir="ltr">{html.escape(record.host) or '—'}</td>
              <td dir="ltr">{html.escape(record.profile_id) or '—'}</td>
              <td>{len(record.features)}</td>
              <td dir="ltr">{html.escape(record.app_image) or '—'}</td>
              <td dir="ltr">{html.escape(record.manifest_issued_at) or '—'}</td>
            </tr>"""
            for record in sorted(records.values(), key=lambda r: r.manifest_issued_at, reverse=True)
        )
        body_table = f"""<div class="table-wrap"><table>
  <thead><tr><th>{L(lang, "مشتری", "Customer")}</th><th>{L(lang, "دامنه", "Domain")}</th><th>{L(lang, "نسخه", "Profile")}</th><th>{L(lang, "فیچر", "Features")}</th><th>{L(lang, "ایمیج", "Image")}</th><th>{L(lang, "آخرین امضا", "Last signed")}</th></tr></thead>
  <tbody>{rows}</tbody>
</table></div>"""
    body = f"""{_page_head(L(lang, "کنسول مدیریت همهٔ استقرارها", "All deployments"), L(lang, "هر استقراری که از همین ماشین امضا یا درون‌ریزی شده، یک‌جا.", "Every deployment signed or imported on this machine, in one place."))}
<div class="stack">
{message_html}
<div class="warning">
  <strong>{L(lang, "فقط بایگانی محلی.", "Local archive only.")}</strong> {L(lang, "این فهرست فقط روی همین ماشین ذخیره می‌شود و به هیچ سروری از هیچ مشتری وصل نمی‌شود. «آخرین امضا» یعنی آخرین چیزی که خودِ همین ابزار امضا کرده — نه وضعیت زندهٔ آن سرور.", "This list is stored only on this machine and is connected to no customer's server. «Last signed» means the last thing this tool signed — not the live state of that server.")}
</div>
{body_table}
<form method="post" action="{_with_lang('/console/import', lang)}">
  <fieldset>
    <legend>{L(lang, "درون‌ریزی manifest امضاشدهٔ موجود", "Import an existing signed manifest")}</legend>
    <p class="card-lead">{L(lang, "برای استقراری که قبلاً — با همین ابزار یا مستقیم با sign_deployment_manifest.py — امضا شده ولی هرگز در این بایگانی ثبت نشده (مثلاً چون پیش از وجود این کنسول امضا شده بود). فقط payload عمومی پرونده خوانده می‌شود: شناسهٔ کلید، شناسهٔ نسخه، فیچرها، زمان صدور. هیچ کلید خصوصی لازم نیست و چیزی دوباره امضا نمی‌شود.", "For a deployment that was signed earlier — with this tool or directly with sign_deployment_manifest.py — but never recorded in this archive (for example because it predates this console). Only the file's public payload is read: key id, profile id, features, issue time. No private key is needed and nothing is re-signed.")}</p>
    <div class="fields">
    <label>{L(lang, "شناسهٔ استقرار (slug)", "Deployment slug")}
      <input type="text" name="import_slug" value="{html.escape(import_slug)}" placeholder="tiara" required dir="ltr">
    </label>
    <label>{L(lang, "مسیر پروندهٔ manifest روی همین ماشین", "Manifest file path, on this machine")}
      <input type="text" name="import_manifest_path" value="{html.escape(import_manifest_path)}" placeholder="manifest.json" required dir="ltr">
    </label>
    <label>{L(lang, "نام نمایشی (اختیاری)", "Display name (optional)")}
      <input type="text" name="import_display_name" value="{html.escape(import_display_name)}" placeholder="TIARA">
    </label>
    <label>{L(lang, "دامنه یا آی‌پی (اختیاری)", "Domain or IP (optional)")}
      <input type="text" name="import_host" value="{html.escape(import_host)}" placeholder="crm.tiara.ir" dir="ltr">
    </label>
    </div>
    <div class="actions"><button type="submit" class="secondary">{L(lang, "درون‌ریزی", "Import")}</button></div>
  </fieldset>
</form>
{import_result_html}
</div>"""
    return _shell(lang, title=L(lang, "کنسول همهٔ استقرارها", "All deployments"), path="/console/", body=body, active="console")


def _console_detail_page(record, *, lang=DEFAULT_LANGUAGE, result_html="", message="", key_id="", private_key_path="",
                          profile_id=None, checked_features=None):
    """`/console/<slug>/` — one recorded deployment: a reissue form
    (pre-filled with its last known profile/features, empty key fields since
    those are never stored), a lightweight bookkeeping-only edit form, and a
    delete action.

    `profile_id`/`checked_features` default to the stored record, but a
    caller re-rendering after a rejected submission passes what was actually
    submitted instead — the same "don't make a mistake mean retyping
    everything" behaviour the quick form already has.
    """
    profile_datalist = _profile_datalist_html()
    effective_profile_id = record.profile_id if profile_id is None else profile_id
    feature_picker = _feature_checkboxes_html(record.features if checked_features is None else checked_features, lang)
    message_html = f'<div class="notice">{html.escape(message)}</div>' if message else ""
    slug = html.escape(record.slug)
    title = record.display_name or record.slug
    confirm = L(
        lang,
        "این رکورد فقط از کنسول محلی حذف می‌شود؛ روی سرور مشتری هیچ اثری ندارد. حذف شود؟",
        "This record is only removed from the local console; it has no effect on the customer's server. Delete it?",
    )
    pattern_title = L(lang, "حروف کوچک لاتین/عدد/underscore/خط‌تیره، شروع با حرف، ۲ تا ۶۴ نویسه",
                      "Lowercase Latin letters, digits, underscore, hyphen; start with a letter; 2–64 characters")
    body = f"""{_page_head(title, L(lang, "امضای مجدد، ویرایش اطلاعات یا حذف رکورد محلی.", "Re-sign, edit the details, or remove the local record."))}
<div class="stack">
{message_html}
<div class="stats">
  <div class="stat"><strong dir="ltr">{slug}</strong><span>{L(lang, "شناسه", "Slug")}</span></div>
  <div class="stat"><strong dir="ltr">{html.escape(record.host) or '—'}</strong><span>{L(lang, "دامنه", "Domain")}</span></div>
  <div class="stat"><strong>{len(record.features)}</strong><span>{L(lang, "فیچر", "Features")}</span></div>
  <div class="stat"><strong dir="ltr" style="font-size:1rem">{html.escape(record.manifest_issued_at) or L(lang, 'هنوز امضا نشده', 'Not signed yet')}</strong><span>{L(lang, "آخرین امضا", "Last signed")}</span></div>
</div>

<form method="post" action="{_with_lang('/console/' + slug + '/reissue', lang)}" class="stack">
  <fieldset>
    <legend>{L(lang, "امضای manifest تازه", "Sign a new manifest")}</legend>
    <div class="fields">
    <label>{L(lang, "شناسهٔ نسخه (profile)", "Profile id")}
      <input type="text" name="profile_id" list="profile-id-options" value="{html.escape(effective_profile_id)}"
             placeholder="client-1" pattern="[a-z][a-z0-9_-]{{1,63}}"
             title="{html.escape(pattern_title)}" required dir="ltr">
      <datalist id="profile-id-options">{profile_datalist}</datalist>
    </label>
    <label>{L(lang, "شناسهٔ کلید (key id)", "Key id")}
      <input type="text" name="key_id" value="{html.escape(key_id or record.key_id)}" placeholder="dolphin-2026" required dir="ltr">
    </label>
    <label class="wide">{L(lang, "مسیر فایل کلید خصوصی، روی همین ماشین (هر بار دوباره وارد کنید — ذخیره نمی‌شود)", "Private key file path, on this machine (enter it every time — it is never stored)")}
      <input type="text" name="private_key_path" value="{html.escape(private_key_path)}"
             placeholder="C:\\keys\\dolphin-manifest-signing.pem" required dir="ltr">
    </label>
    <label class="wide">{L(lang, "ایمیج اپلیکیشن", "Application image")}
      <input type="text" name="deploy_image" value="{html.escape(record.app_image)}" dir="ltr">
    </label>
    </div>
  </fieldset>
  <fieldset>
    <legend>{T(lang, "features_legend")}</legend>
    <div id="picker" data-total-label="{L(lang, 'انتخاب‌شده', 'selected')}">{feature_picker}</div>
  </fieldset>
  <label class="check card"><input type="checkbox" name="regenerate_env" value="1">
    <span>{L(lang, "پیش‌نویس .env تازه هم بساز (رمزهای تصادفی", "Also build a fresh draft .env (")}<strong>{L(lang, "جدید", "new")}</strong>{L(lang, " — فقط اگر واقعاً لازم است)", " random secrets — only if you really need it)")}</span></label>
  <div class="actions" style="margin-top:0"><button type="submit">{L(lang, "امضای manifest تازه", "Sign a new manifest")}</button></div>
</form>
{result_html}

<form method="post" action="{_with_lang('/console/' + slug + '/update', lang)}">
  <fieldset>
    <legend>{L(lang, "ویرایش اطلاعات (بدون نیاز به کلید خصوصی)", "Edit the details (no private key needed)")}</legend>
    <div class="fields">
    <label>{L(lang, "نام نمایشی", "Display name")}
      <input type="text" name="display_name" value="{html.escape(record.display_name)}" placeholder="{slug}">
    </label>
    <label class="wide">{L(lang, "یادداشت", "Notes")}
      <textarea name="notes" rows="3">{html.escape(record.notes)}</textarea>
    </label>
    </div>
    <div class="actions"><button type="submit" class="secondary">{T(lang, "save")}</button></div>
  </fieldset>
</form>

<form method="post" action="{_with_lang('/console/' + slug + '/delete', lang)}"
      onsubmit="return confirm({json.dumps(confirm)});">
  <button type="submit" class="danger">{L(lang, "حذف رکورد از کنسول", "Delete the record from the console")}</button>
</form>
</div>"""
    return _shell(lang, title=f"{title} — {T(lang, 'brand')}", path=f"/console/{record.slug}/", body=body, active="console")


def _not_found_console_page(slug, lang=DEFAULT_LANGUAGE):
    body = f"""{_page_head(L(lang, "استقراری با این شناسه پیدا نشد", "No deployment with this slug was found"))}
<div class="result-error">{L(lang, "هیچ رکوردی با شناسهٔ", "No record with the slug")} <code dir="ltr">{html.escape(slug)}</code> {L(lang, "در کنسول ثبت نشده.", "is recorded in the console.")}</div>"""
    return _shell(lang, title=L(lang, "پیدا نشد", "Not found"), path="/console/", body=body, active="console")


#: Matches `/console/<slug>/` (list is `/console/` alone, handled separately)
#: and `/console/<slug>/<action>` for the reissue/update/delete POST routes.
_CONSOLE_DETAIL_RE = re.compile(r"\A/console/(?P<slug>[^/]+)/\Z")
_CONSOLE_ACTION_RE = re.compile(r"\A/console/(?P<slug>[^/]+)/(?P<action>reissue|update|delete)\Z")


class Handler(BaseHTTPRequestHandler):
    server_version = "DolphinManifestBuilder/1"

    def _refuse_unless_local(self):
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        if host not in ("127.0.0.1", "localhost"):
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"This tool only serves 127.0.0.1 / localhost.")
            return False
        return True

    def _send_html(self, body, status=200):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def _read_form(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        return parse_qs(raw.decode("utf-8"))

    def _path_and_language(self):
        """The path without its query, and the language the query asked for.

        `?lang=` is the only query parameter any of these requests takes, so
        the split is done once here rather than in each branch — and an
        unknown value falls back to Persian rather than rendering a page of
        missing strings (`normalize_language`). The same split serves the
        form posts: each form's action carries the language it was shown in.
        """
        path, _, query = self.path.partition("?")
        values = parse_qs(query).get("lang", [])
        return path, normalize_language(values[0] if values else "")

    def do_GET(self):
        if not self._refuse_unless_local():
            return
        path, lang = self._path_and_language()
        if path == "/start/":
            self._send_html(_landing_page(lang))
            return
        if path == "/":
            self._send_html(_page(lang=lang))
            return
        if path == "/console/":
            self._send_html(_console_list_page(deployment_records.load_all(), lang=lang))
            return
        detail_match = _CONSOLE_DETAIL_RE.match(path)
        if detail_match:
            record = deployment_records.get(detail_match.group("slug"))
            if record is None:
                self._send_html(_not_found_console_page(detail_match.group("slug"), lang), status=404)
                return
            self._send_html(_console_detail_page(record, lang=lang))
            return
        self.send_response(404)
        self.end_headers()

    def _form_page(self, form, lang, result_html, *, keep_key=True):
        def value(name, default=""):
            return form.get(name, [default])[0] or default

        return _page(
            lang=lang,
            profile_id=value("profile_id"),
            key_id=value("key_id") if keep_key else "",
            private_key_path=value("private_key_path") if keep_key else "",
            checked_features=form.get("feature", []),
            deploy_slug=value("deploy_slug"),
            deploy_host=value("deploy_host"),
            deploy_image=value("deploy_image"),
            deploy_manifest_path=value("deploy_manifest_path", "/srv/dolphin/secrets/manifest.json"),
            deploy_retention_days=value("deploy_retention_days", "0"),
            preview_display_name=value("preview_display_name"),
            result_html=result_html,
        )

    def do_POST(self):
        if not self._refuse_unless_local():
            return
        path, lang = self._path_and_language()
        if path == "/build":
            form = self._read_form()
            self._send_html(self._form_page(form, lang, _build_result_html(form, lang)))
            return

        if path == "/preview/start":
            form = self._read_form()
            self._send_html(self._form_page(form, lang, _build_preview_result_html(form, lang), keep_key=False))
            return

        if path == "/preview/stop":
            preview_runner.stop()
            self._redirect(_with_lang("/", lang))
            return

        if path == "/console/import":
            form = self._read_form()
            import_result_html = _build_import_result_html(form, lang)
            self._send_html(_console_list_page(
                deployment_records.load_all(),
                lang=lang,
                import_result_html=import_result_html,
                import_slug=(form.get("import_slug", [""])[0] or ""),
                import_manifest_path=(form.get("import_manifest_path", [""])[0] or ""),
                import_display_name=(form.get("import_display_name", [""])[0] or ""),
                import_host=(form.get("import_host", [""])[0] or ""),
            ))
            return

        action_match = _CONSOLE_ACTION_RE.match(path)
        if not action_match:
            self.send_response(404)
            self.end_headers()
            return

        slug = action_match.group("slug")
        action = action_match.group("action")
        record = deployment_records.get(slug)
        if record is None:
            self._send_html(_not_found_console_page(slug, lang), status=404)
            return

        form = self._read_form()

        if action == "delete":
            # The only console action that removes the page it was called
            # from, so it redirects back to the list rather than re-rendering
            # a detail page for a record that no longer exists.
            deployment_records.delete(slug)
            self._redirect(_with_lang("/console/", lang))
            return

        if action == "update":
            deployment_records.upsert(deployment_records.DeploymentRecord(
                slug=record.slug,
                display_name=(form.get("display_name", [""])[0] or "").strip(),
                host=record.host, profile_id=record.profile_id, features=record.features,
                key_id=record.key_id, app_image=record.app_image,
                manifest_path=record.manifest_path, retention_days=record.retention_days,
                manifest_issued_at=record.manifest_issued_at,
                notes=(form.get("notes", [""])[0] or "").strip(),
            ))
            self._send_html(_console_detail_page(
                deployment_records.get(slug), lang=lang,
                message=L(lang, "اطلاعات ذخیره شد.", "The details were saved."),
            ))
            return

        # action == "reissue"
        result_html = _build_reissue_result_html(record, form, lang)
        self._send_html(_console_detail_page(
            deployment_records.get(slug), lang=lang, result_html=result_html,
            key_id=(form.get("key_id", [""])[0] or ""),
            private_key_path=(form.get("private_key_path", [""])[0] or ""),
            profile_id=(form.get("profile_id", [""])[0] or ""),
            checked_features=form.get("feature", []),
        ))

    def log_message(self, format_string, *args):
        # The default logs the full request line, which for this tool is
        # always "GET /" or "POST /build" — never a query string with
        # anything but the language, since every field (including the key
        # path) travels in the POST body, not the URL. Quieter than the
        # default only in that it drops the client address, which is always
        # 127.0.0.1 here by construction.
        sys.stderr.write(f"{self.log_date_time_string()} {format_string % args}\n")


def _run_desktop_window(url):
    """Open `url` in a real desktop window instead of the default browser.

    `pywebview` is imported here, not at module load time, so every other use
    of this file (the plain browser mode, and every test that imports this
    module by path) never requires it to be installed — only `--desktop`
    does. Not part of `requirements.txt`/`requirements-direct.txt`: those
    describe the shipped container image, and `scripts/` never ships in it
    (see this file's own module docstring); an operator installs this
    locally with `pip install pywebview` (see `scripts/requirements-console.
    txt`), same as any other tool that only ever runs on their own machine.
    """
    try:
        import webview
    except ImportError:
        sys.stderr.write(
            "«--desktop» به pywebview نیاز دارد که نصب نیست:\n"
            "    pip install pywebview\n"
            "یا: pip install -r scripts/requirements-console.txt\n"
            "بدون آن فقط حالت مرورگر معمولی (بدون --desktop) در دسترس است.\n"
        )
        return 1
    # `easy_drag`/native chrome are the library's defaults; only size and
    # title are worth pinning here — everything else about how the window
    # looks is the operating system's own window chrome, not this tool's.
    webview.create_window("کنسول دلفین", url, width=1180, height=820, min_size=(760, 560))
    webview.start()
    return 0


def _self_check():
    """Report what this build can actually see, and fail if it is nothing.

    Written for the frozen `.exe`: a PyInstaller bundle missing one of the
    project packages does not crash, it quietly loses the panel's route
    table and shows every feature as opening no pages. This makes that
    visible as a non-zero exit instead of as a wrong screen.
    """
    features = sorted(FEATURE_DEPENDENCIES)
    pages = _feature_pages()
    gated = sum(len(titles) for titles in pages.values())
    sys.stdout.write(f"features: {len(features)}\n")
    sys.stdout.write(f"features that open pages: {len(pages)}\n")
    sys.stdout.write(f"panel pages behind a feature: {gated}\n")
    if not features:
        sys.stderr.write("no features — the deployment registry did not load.\n")
        return 1
    if not pages:
        sys.stderr.write(
            "no pages — `common.deployment.pages` could not read the panel's "
            "routes. In a frozen build this means a project package was not "
            "bundled; see scripts/build_console_exe.py's COLLECT list.\n"
        )
        return 1
    sys.stdout.write("ok\n")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser tab automatically")
    parser.add_argument(
        "--desktop", action="store_true",
        help="open in a native desktop window instead of the default browser (needs `pip install pywebview`)",
    )
    parser.add_argument(
        "--self-check", action="store_true",
        help=(
            "print what this build can see (features, panel pages) and exit — "
            "what `scripts/build_console_exe.py` runs against the frozen .exe "
            "to prove the project packages really got bundled"
        ),
    )
    arguments = parser.parse_args(argv)

    if arguments.self_check:
        return _self_check()

    server = ThreadingHTTPServer(("127.0.0.1", arguments.port), Handler)
    url = f"http://127.0.0.1:{arguments.port}/"
    # What actually opens is the two-option landing page, not the quick form
    # directly — "the console opens" should ask which of this tool's two
    # jobs the operator is here for, not assume it is always the same one.
    landing_url = f"{url}start/"
    sys.stdout.write(f"Serving on {url} (Ctrl+C to stop). Bound to 127.0.0.1 only.\n")

    if arguments.desktop:
        # The window's own event loop blocks the main thread (on some
        # platforms it must run there), so the HTTP server needs its own
        # thread — the same `ThreadingHTTPServer` already used for every
        # concurrent request, just started explicitly instead of by
        # `serve_forever()` blocking this thread directly.
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            return _run_desktop_window(landing_url)
        finally:
            server.shutdown()
            server.server_close()

    if not arguments.no_browser:
        webbrowser.open(landing_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stdout.write("\nStopped.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
