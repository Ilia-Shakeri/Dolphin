"""Ephemeral local preview of the panel a manifest would produce.

The "پیش‌نمایش زنده" button in `scripts/manifest_builder.py`
(DOLPHIN_FEATURE_MAP_AND_ROADMAP.md §6): boots a REAL, throwaway instance of
this codebase — a fresh SQLite database in a temp directory, migrated,
running `manage.py runserver` on a free local port — so the operator can
click through exactly what a customer's server would show with the ticked
feature set, not a mock-up. If a display name was typed, `custom_branding`
is turned on for the preview and that name is seeded directly into
`common.models.BrandSettings`, so the operator sees the customer's own name
on the panel without visiting `/branding/` by hand first.

The manifest trusted here is signed with a one-time Ed25519 key generated in
memory and never written to disk — never the operator's real signing key.
A preview proves nothing about who is allowed to run a real deployment with
this feature set; it only shows what one would look like. Only `/build`'s
own flow (`manifest_builder._build_result_html`), which asks for the real
key file, produces anything meant to reach a customer's server.

Same boundary as the console itself: the preview server binds to
`127.0.0.1` only. At most one preview runs at a time — starting a new one
stops whatever was running, matching the "one operator, one customer call,
one machine" workflow the console's own docstring describes. `stop()` (and
process exit, via `atexit`) always tears down the subprocess and its temp
directory; nothing here is meant to outlive the console.
"""

import atexit
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from common.deployment.registry import PROFILES  # noqa: E402
from scripts.sign_deployment_manifest import (  # noqa: E402
    build_manifest,
    derive_public_key,
    format_public_key,
)

#: First port tried; `_free_port` walks forward from here if it is taken.
#: Distinct from manifest_builder.py's own default (8799) so the console and
#: a preview it started never collide.
DEFAULT_PORT_START = 8918

#: The one-time login this preview's operator (not the customer) uses to
#: click through it.
PREVIEW_USERNAME = "preview_admin"


class PreviewError(Exception):
    """Something kept the preview from starting; reported without a traceback."""


class PreviewState:
    __slots__ = (
        "process", "temp_dir", "port", "username", "password",
        "display_name", "profile_id", "features", "started_at",
    )

    def __init__(self, **kwargs):
        for name in self.__slots__:
            setattr(self, name, kwargs[name])

    def to_dict(self):
        return {name: getattr(self, name) for name in self.__slots__ if name != "process"}


_lock = Lock()
_current = None  # PreviewState | None


def _free_port(start=DEFAULT_PORT_START, attempts=50):
    for candidate in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return candidate
    raise PreviewError("هیچ پورت محلی آزادی برای پیش‌نمایش پیدا نشد.")


def _wait_until_reachable(port, *, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def _preview_env(*, temp_dir, settings_module, manifest_path, manifest_keys_line):
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    # `temp_dir` first: the settings module and the seed script both live
    # there, and both need `config.settings` importable too, which is why
    # REPOSITORY_ROOT is on this path as well — `manage.py`'s own directory
    # is only auto-added to sys.path when the interpreter's *own* script
    # argument lives there, which is true for `manage.py migrate`/`runserver`
    # but not for the seed script, which is launched from `temp_dir` instead.
    parts = [str(temp_dir), str(REPOSITORY_ROOT)]
    if existing_pythonpath:
        parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["DJANGO_SETTINGS_MODULE"] = settings_module
    env["KARIZ_DEPLOYMENT_MANIFEST"] = str(manifest_path)
    env["KARIZ_DEPLOYMENT_MANIFEST_KEYS"] = manifest_keys_line
    return env


def _write_settings_module(temp_dir, *, db_path, version_label):
    """A settings module that is `config.settings` plus a handful of
    overrides: SQLite instead of PostgreSQL (no real database server needed
    just to look at the panel), and a version string that visibly marks the
    footer as a preview, not a real deployment.

    `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` are overridden explicitly,
    not left to cascade from `DEBUG = True`: `config/settings.py` computes
    both as `not DEBUG` at *its own* import time, using whatever `DEBUG`
    that module resolved (false, by its own default) — a `DEBUG = True`
    line after `from config.settings import *` only rebinds the name `DEBUG`
    in this module's own namespace, it does not go back and recompute a
    value `config.settings` already derived from the old one. Left
    un-overridden, the preview's browser session would never send either
    cookie back over plain `http://127.0.0.1`, and every POST — including
    logging in — would fail CSRF validation before ever reaching a view.
    """
    settings_path = temp_dir / "dolphin_preview_settings.py"
    settings_path.write_text(
        "from config.settings import *\n\n"
        f"DATABASES = {{'default': {{'ENGINE': 'django.db.backends.sqlite3', 'NAME': {str(db_path)!r}}}}}\n"
        "DEBUG = True\n"
        "SESSION_COOKIE_SECURE = False\n"
        "CSRF_COOKIE_SECURE = False\n"
        f"DOLPHIN_VERSION = {version_label!r}\n",
        encoding="utf-8",
    )
    return "dolphin_preview_settings"


def _write_seed_script(temp_dir, *, username, password, display_name):
    """A platform admin to log in as, and — only if a name was typed — the
    same name seeded straight into `BrandSettings` so the preview shows it
    immediately, without the operator visiting `/branding/` first.

    Every value is embedded with `repr()`, not string interpolation, so a
    customer name containing a quote or backslash cannot break the
    generated script — the same reasoning `deployment_records.py` documents
    for its own generated files.
    """
    script_path = temp_dir / "seed_preview.py"
    script_path.write_text(
        "import django\n"
        "django.setup()\n\n"
        "from accounts.models import User\n"
        "from common.models import BrandSettings\n\n"
        f"User.objects.filter(username={username!r}).delete()\n"
        f"User.objects.create_user(username={username!r}, password={password!r}, role=User.Role.PLATFORM_ADMIN)\n\n"
        f"display_name = {display_name!r}\n"
        "if display_name:\n"
        "    BrandSettings.objects.update_or_create(\n"
        "        singleton=BrandSettings.SINGLETON, defaults={'display_name': display_name},\n"
        "    )\n"
        "print('SEEDED')\n",
        encoding="utf-8",
    )
    return script_path


def stop():
    """Stop whatever preview is running, if any. Always safe to call —
    including when nothing is running, and including from `atexit` at
    interpreter shutdown.
    """
    global _current
    with _lock:
        state, _current = _current, None
    if state is None:
        return
    if state.process is not None and state.process.poll() is None:
        state.process.terminate()
        try:
            state.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            state.process.kill()
    if state.temp_dir is not None:
        shutil.rmtree(state.temp_dir, ignore_errors=True)


atexit.register(stop)


def status():
    """The running preview's info (url-building fields, never the process
    object itself), or `None` if nothing is running.
    """
    with _lock:
        return None if _current is None else _current.to_dict()


def start(*, profile_id, features, display_name=""):
    """Stop any running preview and boot a fresh one for this feature set.

    Returns the same shape `status()` does. Raises `PreviewError` — with a
    message safe to show the operator — for anything that stops a preview
    from coming up; nothing partially-started is left behind either way.
    """
    if not features:
        raise PreviewError("دست‌کم یک فیچر لازم است.")
    if profile_id not in PROFILES:
        raise PreviewError(f"شناسهٔ نسخهٔ نامعتبر: {profile_id}")

    stop()

    temp_dir = Path(tempfile.mkdtemp(prefix="dolphin-preview-"))
    try:
        port = _free_port()
        db_path = temp_dir / "preview.sqlite3"

        seed = secrets.token_bytes(32)
        public_key = derive_public_key(seed)
        key_id = "preview"
        issued_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        try:
            manifest_bytes = build_manifest(
                seed=seed, key_id=key_id, profile_id=profile_id, features=sorted(features), issued_at=issued_at,
            )
        except ValueError as error:
            raise PreviewError(str(error)) from error
        manifest_path = temp_dir / "preview-manifest.json"
        manifest_path.write_bytes(manifest_bytes)
        manifest_keys_line = format_public_key(key_id, public_key)

        password = secrets.token_urlsafe(12)
        settings_module = _write_settings_module(
            temp_dir, db_path=db_path, version_label=f"preview-{int(time.time())}",
        )
        seed_script = _write_seed_script(
            temp_dir, username=PREVIEW_USERNAME, password=password, display_name=display_name,
        )
        env = _preview_env(
            temp_dir=temp_dir, settings_module=settings_module,
            manifest_path=manifest_path, manifest_keys_line=manifest_keys_line,
        )

        migrate = subprocess.run(
            [sys.executable, "manage.py", "migrate", "--noinput", f"--settings={settings_module}"],
            cwd=REPOSITORY_ROOT, env=env, capture_output=True, text=True, timeout=180,
        )
        if migrate.returncode != 0:
            raise PreviewError(f"راه‌اندازی دیتابیس پیش‌نمایش شکست خورد: {migrate.stderr.strip()[-800:]}")

        seeded = subprocess.run(
            [sys.executable, str(seed_script)], cwd=REPOSITORY_ROOT, env=env,
            capture_output=True, text=True, timeout=60,
        )
        if seeded.returncode != 0 or "SEEDED" not in seeded.stdout:
            raise PreviewError(f"ساخت کاربر پیش‌نمایش شکست خورد: {seeded.stderr.strip()[-800:]}")

        process = subprocess.Popen(
            [sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}",
             f"--settings={settings_module}", "--noreload"],
            cwd=REPOSITORY_ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if not _wait_until_reachable(port):
            process.terminate()
            raise PreviewError("سرور پیش‌نمایش در زمان مقرر بالا نیامد.")

        state = PreviewState(
            process=process, temp_dir=temp_dir, port=port,
            username=PREVIEW_USERNAME, password=password,
            display_name=display_name, profile_id=profile_id, features=tuple(sorted(features)),
            started_at=issued_at,
        )
        global _current
        with _lock:
            _current = state
        return state.to_dict()
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
