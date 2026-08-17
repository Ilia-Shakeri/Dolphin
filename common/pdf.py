"""Turn an already-rendered print page into PDF bytes.

This deliberately adds **no PDF library**. Correct Persian output needs
contextual Arabic shaping, bidirectional reordering, and TrueType embedding;
a partial implementation of any of those produces broken text, and the three
together are a rendering engine. So instead of writing one, this module hands
the finished HTML to the same engine that already renders the print page
correctly in the browser, and takes back its printed result.

That choice has consequences worth stating plainly:

* **No new Python dependency**, so the hash-pinned lock in `requirements.txt`
  is untouched and does not need regenerating on a Linux host.
* **A browser binary must exist on the host** for the feature to work. It is
  therefore off unless a deployment configures it, and the UI offers the
  download only when the server reports a working renderer — a control that
  cannot act is not shown.
* **The HTML handed over must be self-contained.** `pdf_mode` inlines the
  stylesheet and drops the script, favicon, and toolbar, so the browser makes
  no network request while printing. It is given a throwaway profile
  directory and a timeout, and never a URL from user input.

`docs/ops/MULTI_SERVER_DOCKER_DEPLOYMENT.md` records how to put a browser in
the deployed image, and what that costs.
"""

import contextlib
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.cache import cache


class PdfRendererUnavailable(RuntimeError):
    """No usable renderer, or the renderer failed to produce a PDF."""


class PdfRendererBusy(PdfRendererUnavailable):
    """Every render slot is taken. A retry in a moment will succeed."""


#: Concurrent renders allowed per container. Gunicorn runs synchronous workers,
#: so a render occupies a whole worker for as long as the browser takes — up to
#: PDF_RENDER_TIMEOUT_SECONDS. Left unbounded, three simultaneous downloads
#: occupied all three workers and the application stopped answering anything at
#: all. One slot leaves two workers free to keep serving the site.
PDF_RENDER_SLOTS = 1
_SLOT_KEY = "pdf-render-slot-{index}"


def _setting(name, default):
    return getattr(settings, name, default)


def configured_renderer():
    """The renderer this deployment asked for, or "" when the feature is off."""
    return str(_setting("PDF_RENDERER", "") or "").strip().lower()


def _chromium_binary():
    configured = str(_setting("PDF_CHROMIUM_BINARY", "") or "").strip()
    if configured:
        return configured if Path(configured).is_file() else ""
    # Nothing configured: accept a browser that is simply on PATH, which is the
    # normal case inside a container image that installed one.
    for candidate in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(candidate)
        if found:
            return found
    return ""


def renderer_is_available():
    """True when a PDF really can be produced right now.

    Checked before offering the download, so the button never appears on a
    deployment where pressing it could only fail.
    """
    if configured_renderer() != "chromium":
        return False
    return bool(_chromium_binary())


_STYLESHEET_CACHE = {}


def inline_stylesheet():
    """The application stylesheet as text, for embedding in a print page.

    Read through the staticfiles finders so it works the same whether static
    files are collected or served from the app directory.
    """
    if "css" not in _STYLESHEET_CACHE:
        path = finders.find("common/kariz.css")
        _STYLESHEET_CACHE["css"] = Path(path).read_text(encoding="utf-8") if path else ""
    return _STYLESHEET_CACHE["css"]


@contextlib.contextmanager
def _render_slot():
    """Hold one render slot, or refuse rather than queue.

    `cache.add` is atomic, so the first caller to claim a slot keeps it. The
    entry carries a timeout slightly longer than the render itself, so a worker
    killed mid-render releases its slot instead of stranding it forever.
    """
    timeout = int(_setting("PDF_RENDER_TIMEOUT_SECONDS", 20)) + 5
    token = uuid.uuid4().hex
    for index in range(PDF_RENDER_SLOTS):
        key = _SLOT_KEY.format(index=index)
        if cache.add(key, token, timeout):
            try:
                yield
            finally:
                # Only release a slot still held by this render: if the entry
                # expired and another render claimed it, deleting would hand a
                # second render the same slot.
                if cache.get(key) == token:
                    cache.delete(key)
            return
    raise PdfRendererBusy("The PDF renderer is busy. Try again in a moment.")


def render_html_to_pdf(html):
    """Print a self-contained HTML string and return the PDF bytes.

    Raises `PdfRendererUnavailable` for every failure mode — no renderer, a
    timeout, a non-zero exit, or output that is not a PDF — so a caller never
    has to distinguish "no PDF" from "a file that only looks like one".
    """
    if configured_renderer() != "chromium":
        raise PdfRendererUnavailable("No PDF renderer is configured for this deployment.")
    binary = _chromium_binary()
    if not binary:
        raise PdfRendererUnavailable("The configured PDF renderer binary was not found.")

    timeout = int(_setting("PDF_RENDER_TIMEOUT_SECONDS", 20))
    with _render_slot():
        return _print_with_chromium(html, binary=binary, timeout=timeout)


def _print_with_chromium(html, *, binary, timeout):
    workspace = Path(tempfile.mkdtemp(prefix="kariz-pdf-"))
    try:
        source = workspace / "document.html"
        target = workspace / "document.pdf"
        source.write_text(html, encoding="utf-8")
        command = [
            binary,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-default-apps",
            f"--user-data-dir={workspace / 'profile'}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={target}",
            source.as_uri(),
        ]
        try:
            completed = subprocess.run(
                command, capture_output=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfRendererUnavailable("The PDF renderer timed out.") from exc
        except OSError as exc:
            raise PdfRendererUnavailable("The PDF renderer could not be started.") from exc

        if completed.returncode != 0 or not target.is_file():
            # The renderer's own output can carry host paths, so it is not
            # surfaced to the caller.
            raise PdfRendererUnavailable("The PDF renderer did not produce a document.")
        payload = target.read_bytes()
        if not payload.startswith(b"%PDF"):
            raise PdfRendererUnavailable("The PDF renderer produced an unexpected file.")
        return payload
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
