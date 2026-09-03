"""A small local web form over `sign_deployment_manifest.py` and
`new_deployment.py` (PROFILE-001, Option C) — tick features and fill in one
deployment's identity in a browser instead of running two CLI tools by hand.
This is "Level 1 + Level 2" of the mini-app idea recorded in
`DOLPHIN_FEATURE_MAP_AND_ROADMAP.md` §6: a form that builds a signed manifest
and, optionally, a matching `.env` draft — still no SSH, no server access, no
customer host ever reachable from here.

There is no "brand colour" field, even though the §6 sketch names one: no
setting in this codebase reads a per-deployment brand colour today (branding
is fixed to Dolphin / دلفین — see `CLAUDE.md`'s Branding section), so a field
that fed nothing would be a decoration, not a feature. Add it here only once
some real setting exists to write it into.

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
"""

import argparse
import html
import json
import sys
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from common.deployment.registry import FEATURE_DEPENDENCIES, PROFILES  # noqa: E402
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


def _page(*, profile_id="", key_id="", private_key_path="", checked_features=(),
          deploy_slug="", deploy_host="", deploy_image="", deploy_manifest_path="/srv/dolphin/secrets/manifest.json",
          deploy_retention_days="0", result_html=""):
    """Render the whole page: warning banner, the form (repopulated with
    whatever was just submitted, so a mistake does not mean retyping
    everything), and a result section — success or error — from the last
    submission, if any.
    """
    checked = set(checked_features)
    profile_options = "\n".join(
        f'<option value="{html.escape(pid)}"{" selected" if pid == profile_id else ""}>'
        f'{html.escape(pid)} — {html.escape(description)}</option>'
        for pid, description in sorted(PROFILES.items())
    )
    feature_rows = "\n".join(
        f'<li><label>'
        f'<input type="checkbox" name="feature" value="{html.escape(name)}"'
        f'{" checked" if name in checked else ""} data-requires="{html.escape(",".join(sorted(requires)))}">'
        f' {html.escape(name)}'
        f'{f" <small>(نیازمند: {html.escape(", ".join(sorted(requires)))})</small>" if requires else ""}'
        f'</label></li>'
        for name, requires in sorted(FEATURE_DEPENDENCIES.items())
    )
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<title>ابزار ساخت Manifest</title>
<style>
  body {{ font-family: Tahoma, sans-serif; max-width: 46rem; margin: 2rem auto; padding: 0 1rem; background: #14161c; color: #e4e6eb; }}
  h1 {{ font-size: 1.3rem; }}
  .warning {{ background: #4a1414; border: 1px solid #a33; border-radius: .4rem; padding: .8rem 1rem; margin-bottom: 1.5rem; }}
  fieldset {{ border: 1px solid #3a3d46; border-radius: .4rem; margin-bottom: 1rem; padding: .8rem 1rem; }}
  legend {{ padding: 0 .5rem; }}
  label {{ display: block; margin: .4rem 0; }}
  input[type=text], select {{ width: 100%; box-sizing: border-box; padding: .4rem; background: #1e2028; color: #e4e6eb; border: 1px solid #3a3d46; border-radius: .3rem; }}
  ul {{ list-style: none; padding: 0; margin: 0; columns: 2; }}
  small {{ color: #9aa0ac; }}
  button {{ background: #1b84ff; color: #fff; border: 0; border-radius: .3rem; padding: .6rem 1.2rem; font-size: 1rem; cursor: pointer; }}
  .result-ok {{ background: #12331f; border: 1px solid #2a8a4a; border-radius: .4rem; padding: .8rem 1rem; margin-top: 1.5rem; }}
  .result-error {{ background: #4a1414; border: 1px solid #a33; border-radius: .4rem; padding: .8rem 1rem; margin-top: 1.5rem; }}
  code, pre {{ direction: ltr; text-align: left; display: block; background: #1e2028; padding: .5rem; border-radius: .3rem; overflow-x: auto; unicode-bidi: plaintext; }}
  a.download {{ display: inline-block; margin-top: .5rem; background: #1b84ff; color: #fff; padding: .5rem 1rem; border-radius: .3rem; text-decoration: none; }}
</style>
</head>
<body>
<h1>ابزار ساخت Manifest امضاشده</h1>
<div class="warning">
  <strong>فقط برای مالک پلتفرم.</strong> این ابزار را فقط روی ماشینی اجرا کنید
  که کلید خصوصی امضا رویش نگه‌داری می‌شود — هرگز روی سرور مشتری. کلید خصوصی
  از مسیر فایل زیر خوانده می‌شود؛ هیچ‌جا لاگ، ذخیره یا نمایش داده نمی‌شود.
</div>
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
<script>
// Client-side convenience only — the server resolves dependencies again,
// authoritatively, before it ever signs anything, so a disabled or broken
// script here can make the form less pleasant but never sign an
// inconsistent manifest.
document.getElementById("feature-list").addEventListener("change", (event) => {{
    const box = event.target;
    if (!(box instanceof HTMLInputElement) || box.type !== "checkbox" || !box.checked) return;
    const requires = (box.dataset.requires || "").split(",").filter(Boolean);
    requires.forEach((name) => {{
        const dependency = document.querySelector(`input[name="feature"][value="${{CSS.escape(name)}}"]`);
        if (dependency && !dependency.checked) {{
            dependency.checked = true;
            dependency.dispatchEvent(new Event("change", {{bubbles: true}}));
        }}
    }});
}});
</script>
</body>
</html>"""


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
    env_block = f"""<div class="result-ok">
  <strong>پیش‌نویس .env هم ساخته شد</strong> — رمزهای تصادفی تازه، فقط همین یک بار نمایش داده می‌شوند
  (هیچ‌جای سرور این ابزار ذخیره نمی‌شوند).
  <p><small>پیش از استفادهٔ واقعی: <code>KARIZ_APP_IMAGE</code> و مسیرهای TLS را با مقادیر واقعی
     جایگزین کنید — این‌ها فقط پیش‌نویس‌اند.</small></p>
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
    return manifest_block + env_block


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

    def _send_html(self, body):
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if not self._refuse_unless_local():
            return
        if self.path != "/":
            self.send_response(404)
            self.end_headers()
            return
        self._send_html(_page())

    def do_POST(self):
        if not self._refuse_unless_local():
            return
        if self.path != "/build":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        form = parse_qs(raw.decode("utf-8"))
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
            result_html=result_html,
        ))

    def log_message(self, format_string, *args):
        # The default logs the full request line, which for this tool is
        # always "GET /" or "POST /build" — never a query string, since every
        # field (including the key path) travels in the POST body, not the
        # URL. Quieter than the default only in that it drops the client
        # address, which is always 127.0.0.1 here by construction.
        sys.stderr.write(f"{self.log_date_time_string()} {format_string % args}\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser tab automatically")
    arguments = parser.parse_args(argv)

    server = ThreadingHTTPServer(("127.0.0.1", arguments.port), Handler)
    url = f"http://127.0.0.1:{arguments.port}/"
    sys.stdout.write(f"Serving on {url} (Ctrl+C to stop). Bound to 127.0.0.1 only.\n")
    if not arguments.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stdout.write("\nStopped.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
