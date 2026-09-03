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
    # then open http://127.0.0.1:8799/ in a browser on the same machine

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
import html
import io
import json
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

from common.deployment.registry import FEATURE_DEPENDENCIES, PROFILES  # noqa: E402
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


#: Shared inline CSS for every page this tool serves — the console pages
#: included, so switching between the quick form and the console never
#: looks like switching tools.
_STYLE = """
  body { font-family: Tahoma, sans-serif; max-width: 56rem; margin: 2rem auto; padding: 0 1rem; background: #14161c; color: #e4e6eb; }
  h1 { font-size: 1.3rem; }
  h2 { font-size: 1.1rem; }
  .warning { background: #4a1414; border: 1px solid #a33; border-radius: .4rem; padding: .8rem 1rem; margin-bottom: 1.5rem; }
  .notice { background: #17202b; border: 1px solid #2b3a4a; border-radius: .4rem; padding: .8rem 1rem; margin-bottom: 1.5rem; }
  .preview-live { background: #1b2e12; border: 1px solid #3d8a2a; border-radius: .4rem; padding: .8rem 1rem; margin-bottom: 1.5rem; }
  button.secondary { background: #3a3d46; }
  fieldset { border: 1px solid #3a3d46; border-radius: .4rem; margin-bottom: 1rem; padding: .8rem 1rem; }
  legend { padding: 0 .5rem; }
  label { display: block; margin: .4rem 0; }
  input[type=text], select, textarea { width: 100%; box-sizing: border-box; padding: .4rem; background: #1e2028; color: #e4e6eb; border: 1px solid #3a3d46; border-radius: .3rem; }
  ul { list-style: none; padding: 0; margin: 0; columns: 2; }
  small { color: #9aa0ac; }
  button { background: #1b84ff; color: #fff; border: 0; border-radius: .3rem; padding: .6rem 1.2rem; font-size: 1rem; cursor: pointer; }
  button.danger { background: #a33; }
  .result-ok { background: #12331f; border: 1px solid #2a8a4a; border-radius: .4rem; padding: .8rem 1rem; margin-top: 1.5rem; }
  .result-error { background: #4a1414; border: 1px solid #a33; border-radius: .4rem; padding: .8rem 1rem; margin-top: 1.5rem; }
  code, pre { direction: ltr; text-align: left; display: block; background: #1e2028; padding: .5rem; border-radius: .3rem; overflow-x: auto; unicode-bidi: plaintext; }
  a.download { display: inline-block; margin-top: .5rem; background: #1b84ff; color: #fff; padding: .5rem 1rem; border-radius: .3rem; text-decoration: none; }
  a.nav { color: #6cb2ff; }
  table { width: 100%; border-collapse: collapse; margin-top: .5rem; }
  th, td { text-align: right; padding: .5rem; border-bottom: 1px solid #2a2d36; }
  th { color: #9aa0ac; font-weight: normal; }
"""


def _profile_options_html(profile_id):
    return "\n".join(
        f'<option value="{html.escape(pid)}"{" selected" if pid == profile_id else ""}>'
        f'{html.escape(pid)} — {html.escape(description)}</option>'
        for pid, description in sorted(PROFILES.items())
    )


def _feature_checkboxes_html(checked_features):
    checked = set(checked_features)
    return "\n".join(
        f'<li><label>'
        f'<input type="checkbox" name="feature" value="{html.escape(name)}"'
        f'{" checked" if name in checked else ""} data-requires="{html.escape(",".join(sorted(requires)))}">'
        f' {html.escape(name)}'
        f'{f" <small>(نیازمند: {html.escape(", ".join(sorted(requires)))})</small>" if requires else ""}'
        f'</label></li>'
        for name, requires in sorted(FEATURE_DEPENDENCIES.items())
    )


#: The client-side dependency auto-check script, identical on every page
#: that offers the feature checklist — extracted so the console's pages and
#: the quick form share the exact same behaviour rather than three copies
#: that could drift apart.
_FEATURE_DEPENDENCY_SCRIPT = """
document.getElementById("feature-list").addEventListener("change", (event) => {
    const box = event.target;
    if (!(box instanceof HTMLInputElement) || box.type !== "checkbox" || !box.checked) return;
    const requires = (box.dataset.requires || "").split(",").filter(Boolean);
    requires.forEach((name) => {
        const dependency = document.querySelector(`input[name="feature"][value="${CSS.escape(name)}"]`);
        if (dependency && !dependency.checked) {
            dependency.checked = true;
            dependency.dispatchEvent(new Event("change", {bubbles: true}));
        }
    });
});
"""


def _preview_status_html():
    """A persistent banner, shown on every page load, naming whatever
    preview is currently running (if any) — so the operator never loses
    track of an open preview across other clicks in this tool, and always
    has the stop button and login details in front of them.
    """
    state = preview_runner.status()
    if state is None:
        return ""
    url = f"http://127.0.0.1:{state['port']}/"
    label = html.escape(state["display_name"]) if state["display_name"] else "(بدون نام سفارشی)"
    feature_count = len(state["features"])
    return f"""<div class="preview-live">
  <strong>پیش‌نمایش زنده در حال اجراست</strong> — {label}، {feature_count} فیچر، نسخهٔ {html.escape(state['profile_id'])}.
  <p><a class="nav" href="{url}" target="_blank" rel="noopener">باز کردن پیش‌نمایش ↗</a></p>
  <p><small>ورود پیش‌نمایش — نام کاربری: <code>{html.escape(state['username'])}</code>،
     گذرواژه: <code>{html.escape(state['password'])}</code>. این ورود فقط برای همین پنجرهٔ
     موقت است و با توقف پیش‌نمایش از بین می‌رود.</small></p>
  <form method="post" action="/preview/stop">
    <button type="submit" class="danger">توقف پیش‌نمایش</button>
  </form>
</div>"""


def _page(*, profile_id="", key_id="", private_key_path="", checked_features=(),
          deploy_slug="", deploy_host="", deploy_image="", deploy_manifest_path="/srv/dolphin/secrets/manifest.json",
          deploy_retention_days="0", preview_display_name="", result_html=""):
    """Render the whole page: warning banner, the form (repopulated with
    whatever was just submitted, so a mistake does not mean retyping
    everything), and a result section — success or error — from the last
    submission, if any.
    """
    profile_options = _profile_options_html(profile_id)
    feature_rows = _feature_checkboxes_html(checked_features)
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<title>ابزار ساخت Manifest</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>ابزار ساخت Manifest امضاشده</h1>
<p><a class="nav" href="/console/">→ کنسول مدیریت همهٔ استقرارها</a></p>
<div class="warning">
  <strong>فقط برای مالک پلتفرم.</strong> این ابزار را فقط روی ماشینی اجرا کنید
  که کلید خصوصی امضا رویش نگه‌داری می‌شود — هرگز روی سرور مشتری. کلید خصوصی
  از مسیر فایل زیر خوانده می‌شود؛ هیچ‌جا لاگ، ذخیره یا نمایش داده نمی‌شود.
</div>
{_preview_status_html()}
<form method="post" action="/build">
  <fieldset>
    <legend>هویت manifest</legend>
    <label>شناسهٔ نسخه (profile)
      <select name="profile_id" required>{profile_options}</select>
    </label>
    <label>شناسهٔ کلید (key id)
      <input type="text" name="key_id" value="{html.escape(key_id)}" placeholder="dolphin-2026" required>
    </label>
    <label>مسیر فایل کلید خصوصی، روی همین ماشین
      <input type="text" name="private_key_path" value="{html.escape(private_key_path)}"
             placeholder="C:\\keys\\dolphin-manifest-signing.pem" required>
    </label>
  </fieldset>
  <fieldset>
    <legend>فیچرها</legend>
    <ul id="feature-list">{feature_rows}</ul>
    <p><small>وابستگی‌های ناقص خودکار اضافه می‌شوند (هم همین‌جا موقع تیک‌زدن،
       هم دوباره، قطعی، سمت سرور موقع امضا) — دقیقاً همان قاعده‌ای که
       <code>scripts/new_deployment.py --print-resolved-features</code>
       استفاده می‌کند.</small></p>
  </fieldset>
  <fieldset>
    <legend>پیش‌نمایش زنده (اختیاری، بدون نیاز به کلید خصوصی)</legend>
    <p><small>مشتری زنگ زده، اسم و ماژول‌های موردنظرش را گفته؟ فیچرهای بالا را
       تیک بزنید، اسمش را اینجا بنویسید و «پیش‌نمایش زنده» را بزنید — یک نمونهٔ
       واقعی و موقت از پنل، دقیقاً با همین فیچرها، روی یک پورت محلی دیگر بالا
       می‌آید تا پیش از هر تعهدی کامل چک‌اش کنید. این اسم فقط برای همین
       پیش‌نمایش است؛ نه در manifest/.env خروجی می‌رود و نه جایی ذخیره می‌شود —
       برند واقعی را خودِ مشتری، بعد از استقرار، از <code>/branding/</code> در
       پنل خودش تنظیم می‌کند.</small></p>
    <label>نام مشتری (فقط برای پیش‌نمایش)
      <input type="text" name="preview_display_name" value="{html.escape(preview_display_name)}" placeholder="تیارا">
    </label>
    <button type="submit" formaction="/preview/start" formnovalidate class="secondary">پیش‌نمایش زنده</button>
  </fieldset>
  <fieldset>
    <legend>پیش‌نویس .env (اختیاری — سطح ۲)</legend>
    <p><small>هردو فیلد «شناسهٔ استقرار» و «دامنه یا آی‌پی» را پر کنید تا کنار
       manifest، یک <code>secrets/.env</code> پیش‌نویس هم با رمزهای تصادفی تازه
       ساخته شود — دقیقاً همان چیزی که
       <code>scripts/new_deployment.py</code> می‌سازد. خالی بگذارید تا فقط
       manifest ساخته شود.</small></p>
    <label>شناسهٔ استقرار (slug)
      <input type="text" name="deploy_slug" value="{html.escape(deploy_slug)}" placeholder="tiara">
    </label>
    <label>دامنه یا آی‌پی عمومی
      <input type="text" name="deploy_host" value="{html.escape(deploy_host)}" placeholder="crm.tiara.ir">
    </label>
    <label>ایمیج اپلیکیشن (رفرنس reviewed، با digest)
      <input type="text" name="deploy_image" value="{html.escape(deploy_image)}"
             placeholder="ghcr.io/you/dolphin-app@sha256:...">
    </label>
    <label>مسیر manifest روی سرور مقصد
      <input type="text" name="deploy_manifest_path" value="{html.escape(deploy_manifest_path)}">
    </label>
    <label>نگه‌داری بکاپ (روز، ۰ یعنی همیشه)
      <input type="text" name="deploy_retention_days" value="{html.escape(deploy_retention_days)}">
    </label>
  </fieldset>
  <button type="submit">ساخت و امضای Manifest</button>
</form>
{result_html}
<script>{_FEATURE_DEPENDENCY_SCRIPT}</script>
</body>
</html>"""


def _deploy_steps_text(*, slug, host, image, manifest_keys_line, manifest_path):
    """The short, customer-specific cheat sheet bundled into the deployment
    zip — not a copy of the runbook (which stays the single source of truth
    and could drift from a duplicated copy), just this deployment's own
    values dropped into the one command `docs/ops/DOLPHIN_DEPLOYMENT_
    RUNBOOK.md` section 1.0 already documents as the one-command path.
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


def _build_result_html(form):
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
        if profile_id not in PROFILES:
            raise ProvisioningError("شناسهٔ نسخه نامعتبر است.")
        if not key_id:
            raise ProvisioningError("شناسهٔ کلید الزامی است.")
        if not private_key_path:
            raise ProvisioningError("مسیر فایل کلید خصوصی الزامی است.")
        if not requested_features:
            raise ProvisioningError("دست‌کم یک فیچر را تیک بزنید.")

        # The .env fields are all-or-nothing: either both slug and host are
        # given and a full draft is generated, or neither is and this call
        # behaves exactly like Level 1 (manifest only). One filled in without
        # the other is treated as a mistake, not a partial request — a slug
        # with no host cannot become DJANGO_ALLOWED_HOSTS, and a host with no
        # slug cannot name a database.
        want_env = bool(deploy_slug or deploy_host)
        if want_env:
            if not deploy_slug or not deploy_host:
                raise ProvisioningError(
                    "برای پیش‌نویس .env هم «شناسهٔ استقرار» و هم «دامنه یا آی‌پی» لازم است."
                )
            if not SLUG_PATTERN.match(deploy_slug) or deploy_slug.startswith("pg_"):
                raise ProvisioningError(
                    "شناسهٔ استقرار باید ۲ تا ۴۱ کاراکتر، حروف کوچک لاتین، شروع‌شونده با حرف "
                    "باشد و نباید با pg_ شروع شود — نام دیتابیس و نقش‌های PostgreSQL از رویش ساخته می‌شود."
                )
            if not HOST_PATTERN.match(deploy_host):
                raise ProvisioningError("دامنه یا آی‌پی نامعتبر است — بدون scheme، پورت یا مسیر.")
            try:
                deploy_retention_days = int(deploy_retention_days_raw)
                if deploy_retention_days < 0:
                    raise ValueError
            except ValueError as error:
                raise ProvisioningError("نگه‌داری بکاپ باید یک عدد صحیح غیرمنفی باشد.") from error

        features, added = resolve_features(requested_features)
        seed = read_private_seed(private_key_path)
        public_key = derive_public_key(seed)
        issued_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        manifest_bytes = build_manifest(
            seed=seed, key_id=key_id, profile_id=profile_id,
            features=sorted(features), issued_at=issued_at,
        )
    except (ProvisioningError, ProvisioningLikeError, ValueError, OSError) as error:
        return f'<div class="result-error"><strong>ساخته نشد:</strong> {html.escape(str(error))}</div>'

    manifest_json = json.dumps(json.loads(manifest_bytes), ensure_ascii=False, indent=2)
    manifest_b64 = manifest_bytes.hex()  # re-decoded client-side below; avoids a second HTTP round trip for the download
    public_key_line = format_public_key(key_id, public_key)
    added_note = ""
    if added:
        added_list = ", ".join(
            f"{feature} (نیازمند {', '.join(sorted(requires))})" for feature, requires in sorted(added.items())
        )
        added_note = f"<p>به‌خاطر وابستگی، این‌ها هم اضافه شدند: {html.escape(added_list)}</p>"

    feature_list = "، ".join(sorted(features))
    manifest_block = f"""<div class="result-ok">
  <strong>Manifest ساخته و امضا شد</strong> — {len(features)} فیچر، نسخهٔ {html.escape(profile_id)}.
  {added_note}
  <p>فیچرهای نهاییِ امضاشده: {html.escape(feature_list)}</p>
  <p>کلید عمومی — این خط را عیناً در <code>KARIZ_DEPLOYMENT_MANIFEST_KEYS</code> بگذارید:</p>
  <pre>{html.escape(public_key_line)}</pre>
  <a class="download" download="manifest.json" id="download-link" href="#">دانلود manifest.json</a>
  <script>
    (() => {{
      const hex = "{manifest_b64}";
      const bytes = new Uint8Array(hex.match(/.{{2}}/g).map((pair) => parseInt(pair, 16)));
      const url = URL.createObjectURL(new Blob([bytes], {{type: "application/json"}}));
      document.getElementById("download-link").href = url;
    }})();
  </script>
  <p><small>محتوای فایل:</small></p>
  <pre>{html.escape(manifest_json)}</pre>
</div>"""

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
    console_note = ""
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
            f'<p><small>در کنسول هم ثبت شد: '
            f'<a class="nav" href="/console/{html.escape(deploy_slug)}/">{html.escape(deploy_slug)}</a></small></p>'
        )
    except deployment_records.DeploymentRecordError:
        console_note = '<p><small>ثبت در کنسول ناموفق بود؛ خودِ manifest و .env بالا هنوز معتبرند.</small></p>'

    deploy_steps_text = _deploy_steps_text(
        slug=deploy_slug, host=deploy_host, image=deploy_image,
        manifest_keys_line=public_key_line, manifest_path=deploy_manifest_path,
    )
    bundle_hex = _deployment_bundle_zip_hex(
        manifest_bytes=manifest_bytes, env_content=env_content, deploy_steps_text=deploy_steps_text,
    )

    env_block = f"""<div class="result-ok">
  <strong>پیش‌نویس .env هم ساخته شد</strong> — رمزهای تصادفی تازه، فقط همین یک بار نمایش داده می‌شوند
  (هیچ‌جای سرور این ابزار ذخیره نمی‌شوند).
  <p><small>پیش از استفادهٔ واقعی: <code>KARIZ_APP_IMAGE</code> و مسیرهای TLS را با مقادیر واقعی
     جایگزین کنید — این‌ها فقط پیش‌نویس‌اند.</small></p>
  {console_note}
  <p>
    <a class="download" download="dolphin-deploy-{html.escape(deploy_slug)}.zip" id="download-link-bundle" href="#">دانلود بستهٔ استقرار (zip)</a>
    <small>— manifest.json + dolphin.env + راهنمای گام‌به‌گام، یک فایل برای کپی به سرور مشتری.</small>
  </p>
  <script>
    (() => {{
      const hex = "{bundle_hex}";
      const bytes = new Uint8Array(hex.match(/.{{2}}/g).map((pair) => parseInt(pair, 16)));
      const url = URL.createObjectURL(new Blob([bytes], {{type: "application/zip"}}));
      document.getElementById("download-link-bundle").href = url;
    }})();
  </script>
  <a class="download" download="dolphin.env" id="download-link-env" href="#">دانلود .env (تکی)</a>
  <script>
    (() => {{
      const hex = "{env_hex}";
      const bytes = new Uint8Array(hex.match(/.{{2}}/g).map((pair) => parseInt(pair, 16)));
      const url = URL.createObjectURL(new Blob([bytes], {{type: "text/plain"}}));
      document.getElementById("download-link-env").href = url;
    }})();
  </script>
  <p><small>محتوای فایل:</small></p>
  <pre>{html.escape(env_content)}</pre>
</div>"""
    return manifest_block + env_block


def _build_preview_result_html(form):
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

    if profile_id not in PROFILES:
        return '<div class="result-error"><strong>پیش‌نمایش ساخته نشد:</strong> شناسهٔ نسخه نامعتبر است.</div>'
    if not requested_features:
        return '<div class="result-error"><strong>پیش‌نمایش ساخته نشد:</strong> دست‌کم یک فیچر را تیک بزنید.</div>'

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
        return f'<div class="result-error"><strong>پیش‌نمایش ساخته نشد:</strong> {html.escape(str(error))}</div>'

    try:
        preview_runner.start(profile_id=profile_id, features=features, display_name=display_name)
    except preview_runner.PreviewError as error:
        return f'<div class="result-error"><strong>پیش‌نمایش بالا نیامد:</strong> {html.escape(str(error))}</div>'
    except Exception as error:  # noqa: BLE001 — a subprocess/OS failure here
        # must become a readable message, never a stack trace in the
        # browser (the same guarantee `_build_result_html` gives for
        # signing failures) — `preview_runner.start` already guarantees any
        # partially-started subprocess/temp directory was cleaned up before
        # this was raised.
        return f'<div class="result-error"><strong>پیش‌نمایش بالا نیامد:</strong> {html.escape(str(error))}</div>'
    return ""


def _build_reissue_result_html(record, form):
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
        if profile_id not in PROFILES:
            raise ProvisioningError("شناسهٔ نسخه نامعتبر است.")
        if not key_id:
            raise ProvisioningError("شناسهٔ کلید الزامی است.")
        if not private_key_path:
            raise ProvisioningError("مسیر فایل کلید خصوصی الزامی است.")
        if not requested_features:
            raise ProvisioningError("دست‌کم یک فیچر را تیک بزنید.")

        features, added = resolve_features(requested_features)
        seed = read_private_seed(private_key_path)
        public_key = derive_public_key(seed)
        issued_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        manifest_bytes = build_manifest(
            seed=seed, key_id=key_id, profile_id=profile_id,
            features=sorted(features), issued_at=issued_at,
        )
    except (ProvisioningError, ProvisioningLikeError, ValueError, OSError) as error:
        return f'<div class="result-error"><strong>ساخته نشد:</strong> {html.escape(str(error))}</div>'

    manifest_json = json.dumps(json.loads(manifest_bytes), ensure_ascii=False, indent=2)
    manifest_b64 = manifest_bytes.hex()
    public_key_line = format_public_key(key_id, public_key)
    added_note = ""
    if added:
        added_list = ", ".join(
            f"{feature} (نیازمند {', '.join(sorted(requires))})" for feature, requires in sorted(added.items())
        )
        added_note = f"<p>به‌خاطر وابستگی، این‌ها هم اضافه شدند: {html.escape(added_list)}</p>"

    feature_list = "، ".join(sorted(features))
    manifest_block = f"""<div class="result-ok">
  <strong>Manifest تازه ساخته و امضا شد</strong> — {len(features)} فیچر، نسخهٔ {html.escape(profile_id)}.
  {added_note}
  <p>فیچرهای نهاییِ امضاشده: {html.escape(feature_list)}</p>
  <p>کلید عمومی — این خط را عیناً در <code>KARIZ_DEPLOYMENT_MANIFEST_KEYS</code> بگذارید:</p>
  <pre>{html.escape(public_key_line)}</pre>
  <a class="download" download="manifest.json" id="download-link" href="#">دانلود manifest.json</a>
  <script>
    (() => {{
      const hex = "{manifest_b64}";
      const bytes = new Uint8Array(hex.match(/.{{2}}/g).map((pair) => parseInt(pair, 16)));
      const url = URL.createObjectURL(new Blob([bytes], {{type: "application/json"}}));
      document.getElementById("download-link").href = url;
    }})();
  </script>
  <p><small>محتوای فایل:</small></p>
  <pre>{html.escape(manifest_json)}</pre>
</div>"""

    env_block = ""
    if regenerate_env:
        env_content = "\n".join(env_lines(
            slug=record.slug, host=record.host, image=deploy_image, profile=profile_id,
            manifest_path=record.manifest_path, manifest_keys=public_key_line,
            retention_days=record.retention_days,
        ))
        env_hex = env_content.encode("utf-8").hex()
        env_block = f"""<div class="result-ok">
  <strong>پیش‌نویس .env تازه هم ساخته شد</strong> — رمزهای تصادفی تازه، فقط همین یک بار نمایش داده می‌شوند.
  <p><small>این رمزها با آنچه سرور مشتری همین الان اجرا می‌کند فرق دارد — پیش از استفادهٔ واقعی،
     رمزهای دیتابیس/سرویس‌ها را روی خودِ سرور هم به‌روز کنید، وگرنه سرویس بالا نمی‌آید.</small></p>
  <a class="download" download="dolphin.env" id="download-link-env" href="#">دانلود .env</a>
  <script>
    (() => {{
      const hex = "{env_hex}";
      const bytes = new Uint8Array(hex.match(/.{{2}}/g).map((pair) => parseInt(pair, 16)));
      const url = URL.createObjectURL(new Blob([bytes], {{type: "text/plain"}}));
      document.getElementById("download-link-env").href = url;
    }})();
  </script>
  <p><small>محتوای فایل:</small></p>
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


def _console_list_page(records, *, message=""):
    """`/console/` — every deployment recorded so far, newest signature
    first. This is purely a read of `deployment_records.load_all()`; nothing
    here reaches any customer host.
    """
    message_html = f'<div class="notice">{html.escape(message)}</div>' if message else ""
    if not records:
        body = (
            '<p>هنوز هیچ استقراری در کنسول ثبت نشده. برای ثبت اولین مورد، '
            '<a class="nav" href="/">فرم ساخت manifest</a> را با «شناسهٔ استقرار» و '
            '«دامنه یا آی‌پی» پر کنید.</p>'
        )
    else:
        rows = "\n".join(
            f"""<tr>
              <td><a class="nav" href="/console/{html.escape(record.slug)}/">{html.escape(record.display_name or record.slug)}</a></td>
              <td dir="ltr">{html.escape(record.host) or '—'}</td>
              <td>{html.escape(record.profile_id) or '—'}</td>
              <td>{len(record.features)}</td>
              <td dir="ltr">{html.escape(record.app_image) or '—'}</td>
              <td dir="ltr">{html.escape(record.manifest_issued_at) or '—'}</td>
            </tr>"""
            for record in sorted(records.values(), key=lambda r: r.manifest_issued_at, reverse=True)
        )
        body = f"""<table>
  <thead><tr><th>مشتری</th><th>دامنه</th><th>نسخه</th><th>فیچر</th><th>ایمیج</th><th>آخرین امضا</th></tr></thead>
  <tbody>{rows}</tbody>
</table>"""
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<title>کنسول همهٔ استقرارها</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>کنسول مدیریت همهٔ استقرارها</h1>
<p><a class="nav" href="/">→ فرم ساخت manifest تکی</a></p>
{message_html}
<div class="warning">
  <strong>فقط بایگانی محلی.</strong> این فهرست فقط روی همین ماشین ذخیره می‌شود و به هیچ سروری
  از هیچ مشتری وصل نمی‌شود. «آخرین امضا» یعنی آخرین چیزی که خودِ همین ابزار امضا کرده — نه
  وضعیت زندهٔ آن سرور.
</div>
{body}
</body>
</html>"""


def _console_detail_page(record, *, result_html="", message="", key_id="", private_key_path="",
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
    profile_options = _profile_options_html(record.profile_id if profile_id is None else profile_id)
    feature_rows = _feature_checkboxes_html(record.features if checked_features is None else checked_features)
    message_html = f'<div class="notice">{html.escape(message)}</div>' if message else ""
    slug = html.escape(record.slug)
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<title>{html.escape(record.display_name or record.slug)} — کنسول</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>{html.escape(record.display_name or record.slug)}</h1>
<p><a class="nav" href="/console/">→ کنسول همهٔ استقرارها</a></p>
{message_html}
<div class="notice">
  شناسه: <code dir="ltr">{slug}</code> —
  دامنه: <code dir="ltr">{html.escape(record.host) or '—'}</code> —
  آخرین امضا: <code dir="ltr">{html.escape(record.manifest_issued_at) or 'هنوز امضا نشده'}</code>
</div>

<form method="post" action="/console/{slug}/reissue">
  <fieldset>
    <legend>امضای manifest تازه</legend>
    <label>شناسهٔ نسخه (profile)
      <select name="profile_id" required>{profile_options}</select>
    </label>
    <label>شناسهٔ کلید (key id)
      <input type="text" name="key_id" value="{html.escape(key_id or record.key_id)}" placeholder="dolphin-2026" required>
    </label>
    <label>مسیر فایل کلید خصوصی، روی همین ماشین (هر بار دوباره وارد کنید — ذخیره نمی‌شود)
      <input type="text" name="private_key_path" value="{html.escape(private_key_path)}"
             placeholder="C:\\keys\\dolphin-manifest-signing.pem" required>
    </label>
    <ul id="feature-list">{feature_rows}</ul>
    <label>ایمیج اپلیکیشن
      <input type="text" name="deploy_image" value="{html.escape(record.app_image)}">
    </label>
    <label><input type="checkbox" name="regenerate_env" value="1">
      پیش‌نویس .env تازه هم بساز (رمزهای تصادفی <strong>جدید</strong> — فقط اگر واقعاً لازم است)</label>
  </fieldset>
  <button type="submit">امضای manifest تازه</button>
</form>
{result_html}
<script>{_FEATURE_DEPENDENCY_SCRIPT}</script>

<form method="post" action="/console/{slug}/update">
  <fieldset>
    <legend>ویرایش اطلاعات (بدون نیاز به کلید خصوصی)</legend>
    <label>نام نمایشی
      <input type="text" name="display_name" value="{html.escape(record.display_name)}" placeholder="{slug}">
    </label>
    <label>یادداشت
      <textarea name="notes" rows="3">{html.escape(record.notes)}</textarea>
    </label>
  </fieldset>
  <button type="submit">ذخیره</button>
</form>

<form method="post" action="/console/{slug}/delete"
      onsubmit="return confirm('این رکورد فقط از کنسول محلی حذف می‌شود؛ روی سرور مشتری هیچ اثری ندارد. حذف شود؟');">
  <button type="submit" class="danger">حذف رکورد از کنسول</button>
</form>
</body>
</html>"""


def _not_found_console_page(slug):
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head><meta charset="utf-8"><title>پیدا نشد</title><style>{_STYLE}</style></head>
<body>
<h1>استقراری با این شناسه پیدا نشد</h1>
<p><a class="nav" href="/console/">→ کنسول همهٔ استقرارها</a></p>
<div class="result-error">هیچ رکوردی با شناسهٔ <code dir="ltr">{html.escape(slug)}</code> در کنسول ثبت نشده.</div>
</body>
</html>"""


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

    def do_GET(self):
        if not self._refuse_unless_local():
            return
        if self.path == "/":
            self._send_html(_page())
            return
        if self.path == "/console/":
            self._send_html(_console_list_page(deployment_records.load_all()))
            return
        detail_match = _CONSOLE_DETAIL_RE.match(self.path)
        if detail_match:
            record = deployment_records.get(detail_match.group("slug"))
            if record is None:
                self._send_html(_not_found_console_page(detail_match.group("slug")), status=404)
                return
            self._send_html(_console_detail_page(record))
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if not self._refuse_unless_local():
            return
        if self.path == "/build":
            form = self._read_form()
            result_html = _build_result_html(form)
            self._send_html(_page(
                profile_id=(form.get("profile_id", [""])[0] or ""),
                key_id=(form.get("key_id", [""])[0] or ""),
                private_key_path=(form.get("private_key_path", [""])[0] or ""),
                checked_features=form.get("feature", []),
                deploy_slug=(form.get("deploy_slug", [""])[0] or ""),
                deploy_host=(form.get("deploy_host", [""])[0] or ""),
                deploy_image=(form.get("deploy_image", [""])[0] or ""),
                deploy_manifest_path=(form.get("deploy_manifest_path", [""])[0] or "/srv/dolphin/secrets/manifest.json"),
                deploy_retention_days=(form.get("deploy_retention_days", [""])[0] or "0"),
                preview_display_name=(form.get("preview_display_name", [""])[0] or ""),
                result_html=result_html,
            ))
            return

        if self.path == "/preview/start":
            form = self._read_form()
            result_html = _build_preview_result_html(form)
            self._send_html(_page(
                profile_id=(form.get("profile_id", [""])[0] or ""),
                checked_features=form.get("feature", []),
                deploy_slug=(form.get("deploy_slug", [""])[0] or ""),
                deploy_host=(form.get("deploy_host", [""])[0] or ""),
                deploy_image=(form.get("deploy_image", [""])[0] or ""),
                deploy_manifest_path=(form.get("deploy_manifest_path", [""])[0] or "/srv/dolphin/secrets/manifest.json"),
                deploy_retention_days=(form.get("deploy_retention_days", [""])[0] or "0"),
                preview_display_name=(form.get("preview_display_name", [""])[0] or ""),
                result_html=result_html,
            ))
            return

        if self.path == "/preview/stop":
            preview_runner.stop()
            self._redirect("/")
            return

        action_match = _CONSOLE_ACTION_RE.match(self.path)
        if not action_match:
            self.send_response(404)
            self.end_headers()
            return

        slug = action_match.group("slug")
        action = action_match.group("action")
        record = deployment_records.get(slug)
        if record is None:
            self._send_html(_not_found_console_page(slug), status=404)
            return

        form = self._read_form()

        if action == "delete":
            # The only console action that removes the page it was called
            # from, so it redirects back to the list rather than re-rendering
            # a detail page for a record that no longer exists.
            deployment_records.delete(slug)
            self._redirect("/console/")
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
                deployment_records.get(slug), message="اطلاعات ذخیره شد.",
            ))
            return

        # action == "reissue"
        result_html = _build_reissue_result_html(record, form)
        self._send_html(_console_detail_page(
            deployment_records.get(slug), result_html=result_html,
            key_id=(form.get("key_id", [""])[0] or ""),
            private_key_path=(form.get("private_key_path", [""])[0] or ""),
            profile_id=(form.get("profile_id", [""])[0] or ""),
            checked_features=form.get("feature", []),
        ))

    def log_message(self, format_string, *args):
        # The default logs the full request line, which for this tool is
        # always "GET /" or "POST /build" — never a query string, since every
        # field (including the key path) travels in the POST body, not the
        # URL. Quieter than the default only in that it drops the client
        # address, which is always 127.0.0.1 here by construction.
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser tab automatically")
    parser.add_argument(
        "--desktop", action="store_true",
        help="open in a native desktop window instead of the default browser (needs `pip install pywebview`)",
    )
    arguments = parser.parse_args(argv)

    server = ThreadingHTTPServer(("127.0.0.1", arguments.port), Handler)
    url = f"http://127.0.0.1:{arguments.port}/"
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
            return _run_desktop_window(url)
        finally:
            server.shutdown()
            server.server_close()

    if not arguments.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stdout.write("\nStopped.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
