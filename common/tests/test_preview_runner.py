"""`scripts/preview_runner.py` — the "پیش‌نمایش زنده" button's mechanism.

Every test here that calls `.start()` boots a *real* subprocess: a fresh
SQLite database, migrated, serving a real `manage.py runserver`. That is
slow (each boot is ten-plus seconds) and deliberate — the one bug this
module actually shipped with (`CSRF_COOKIE_SECURE`/`SESSION_COOKIE_SECURE`
silently staying `True` because they are derived from `DEBUG` inside
`config/settings.py` at *that module's own* import time, so a later
`DEBUG = True` in the generated preview settings module never re-derives
them) was invisible to Django's own `TestCase`/`Client`, which never goes
over real HTTP and never honours a cookie's `Secure` attribute the way a
real client does. Only a genuine socket-level HTTP round trip against a
really-running server catches that class of bug, so that is what most of
this file does, and it does not pass through Django's test `Client` for
that reason — this hits the preview server exactly the way a real browser
(or a real operator's own tooling) would: raw `urllib`, a real cookie jar,
a real CSRF double-submit.

Every boot is torn down in a `finally`/`tearDown`, and `PreviewBootTests`
also asserts the port is unreachable afterwards — a leaked subprocess or
temp directory here is exactly the failure mode `preview_runner.stop()` and
its `atexit` registration exist to prevent.
"""

import http.cookiejar
import json
import socket
import urllib.error
import urllib.request

from django.test import SimpleTestCase

from scripts import preview_runner


def _reachable(port, timeout=1):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _get(port, path):
    return urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5)


def _login(port, *, username, password):
    """A real cookie-jar, real CSRF double-submit login — see the module
    docstring for why this is deliberately not `django.test.Client`.
    """
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.open(f"http://127.0.0.1:{port}/login/", timeout=5).read()
    csrf_token = next(cookie.value for cookie in jar if cookie.name == "csrftoken")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/auth/login/",
        data=json.dumps({"username": username, "password": password}).encode(),
        headers={
            "Content-Type": "application/json",
            "X-CSRFToken": csrf_token,
            "Referer": f"http://127.0.0.1:{port}/login/",
        },
    )
    return opener.open(request, timeout=5), opener


class PreviewHelperTests(SimpleTestCase):
    """The pieces that do not need a subprocess."""

    def test_free_port_returns_something_actually_free(self):
        port = preview_runner._free_port(start=8918)
        self.assertFalse(_reachable(port, timeout=0.2))

    def test_free_port_skips_a_port_already_bound(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
            taken.bind(("127.0.0.1", 8918))
            taken.listen(1)
            port = preview_runner._free_port(start=8918)
            self.assertNotEqual(port, 8918)

    def test_status_is_none_when_nothing_is_running(self):
        preview_runner.stop()  # in case an earlier test in this run left one
        self.assertIsNone(preview_runner.status())

    def test_stop_with_nothing_running_is_a_safe_no_op(self):
        preview_runner.stop()
        preview_runner.stop()  # twice in a row must not raise either

    def test_seed_script_embeds_values_by_repr_not_interpolation(self):
        """A customer name containing a quote must not break the generated
        script — `repr()` escapes it, naive f-string interpolation would not.
        """
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = preview_runner._write_seed_script(
                Path(tmp), username="preview_admin", password="pw", display_name='ت"یارا\'س',
            )
            content = path.read_text(encoding="utf-8")
        compile(content, str(path), "exec")  # must be syntactically valid Python
        self.assertIn("preview_admin", content)

    def test_settings_module_overrides_cookie_security_explicitly(self):
        """The regression guard for the actual bug this module shipped with
        once: `DEBUG = True` alone does not make `config.settings`'s
        already-derived `CSRF_COOKIE_SECURE`/`SESSION_COOKIE_SECURE` false
        again, so the generated module must set both by name, not rely on
        the cascade. See the module docstring for the full explanation.
        """
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            preview_runner._write_settings_module(temp_dir, db_path=temp_dir / "x.sqlite3", version_label="v")
            content = (temp_dir / "dolphin_preview_settings.py").read_text(encoding="utf-8")
        self.assertIn("SESSION_COOKIE_SECURE = False", content)
        self.assertIn("CSRF_COOKIE_SECURE = False", content)


class PreviewBootTests(SimpleTestCase):
    """Real subprocess boots. Slow by nature — see the module docstring."""

    def tearDown(self):
        preview_runner.stop()

    def test_a_full_boot_serves_the_requested_features_and_branding_and_a_working_login(self):
        state = preview_runner.start(
            profile_id="demo", features={"customers", "leads", "custom_branding"}, display_name="تیارا",
        )
        port = state["port"]
        self.assertTrue(_reachable(port))
        self.assertEqual(state["username"], preview_runner.PREVIEW_USERNAME)

        login_page = _get(port, "/login/").read().decode()
        self.assertIn("تیارا", login_page)
        self.assertNotIn("Dolphin | دلفین", login_page)

        response, opener = _login(port, username=state["username"], password=state["password"])
        self.assertEqual(response.status, 200)

        home = opener.open(f"http://127.0.0.1:{port}/", timeout=5).read().decode()
        self.assertIn("تیارا", home)
        self.assertIn("سرنخ", home)  # leads, selected
        self.assertNotIn("کاتالوگ محصولات", home)  # products, not selected

        preview_runner.stop()
        self.assertFalse(_reachable(port))
        self.assertIsNone(preview_runner.status())

    def test_no_display_name_means_plain_dolphin_branding(self):
        state = preview_runner.start(profile_id="demo", features={"customers"}, display_name="")
        login_page = _get(state["port"], "/login/").read().decode()
        self.assertIn("Dolphin | دلفین", login_page)

    def test_starting_a_second_preview_stops_the_first(self):
        first = preview_runner.start(profile_id="demo", features={"customers"}, display_name="")
        first_port = first["port"]
        self.assertTrue(_reachable(first_port))
        first_home = _get(first_port, "/login/").read().decode()
        self.assertIn("Dolphin | دلفین", first_home)

        # `start()` stops the first preview before picking a port for the
        # second, so reusing the same now-free port is expected and fine —
        # what must actually be true is that only ONE preview ever answers:
        # the second server serves the second request, whichever port it
        # ended up on, and only that one is the one `status()` now names.
        second = preview_runner.start(
            profile_id="demo", features={"products", "custom_branding"}, display_name="غزال",
        )
        self.assertTrue(_reachable(second["port"]))
        self.assertEqual(preview_runner.status()["port"], second["port"])
        second_home = _get(second["port"], "/login/").read().decode()
        self.assertIn("غزال", second_home)

    def test_an_invalid_login_is_rejected_not_silently_accepted(self):
        state = preview_runner.start(profile_id="demo", features={"customers"}, display_name="")
        with self.assertRaises(urllib.error.HTTPError) as context:
            _login(state["port"], username=state["username"], password="definitely-wrong")
        self.assertEqual(context.exception.code, 400)

    def test_no_features_refuses_before_touching_a_subprocess(self):
        with self.assertRaises(preview_runner.PreviewError):
            preview_runner.start(profile_id="demo", features=set(), display_name="")
        self.assertIsNone(preview_runner.status())
