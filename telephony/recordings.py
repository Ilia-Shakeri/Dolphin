"""Call recordings, streamed through Dolphin (2.22.0, decision D13).

The PBX keeps the audio; Dolphin keeps only the reference. A recording is
served by `GET /api/v1/calls/<id>/recording/` after the caller's permission
and scope are checked, with HTTP `Range` support so a browser can seek. The
recordings directory is never exposed on its own.

Two ways to reach the file, per connection:

* `mount` — the PBX's recordings directory mounted read-only on the Dolphin
  host (NFS/SSHFS) at `recordings_path`. FreePBX files recordings under
  `YYYY/MM/DD/`; the call's own date finds the folder.
* `url` — the PBX serves recordings over HTTPS to Dolphin only; the file is
  fetched from `recordings_base_url` and passed through, `Range` included.

Only audio files are served, and a path that would leave the recordings root
(`..`, an absolute path, a symlink out) is refused.
"""

import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlsplit

from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone

CONTENT_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".gsm": "audio/x-gsm",
    ".wav49": "audio/wav",
}
CHUNK = 64 * 1024
URL_TIMEOUT = 15
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


class RecordingUnavailable(Exception):
    pass


class RangeNotSatisfiable(Exception):
    pass


def parse_range(header, size):
    """`(start, end)` inclusive for one `bytes=` range, `None` for the whole
    file; `RangeNotSatisfiable` for anything outside it. Multiple ranges are
    answered with the whole file, which the RFC allows."""
    if not header:
        return None
    match = _RANGE.match(header.strip())
    if not match:
        return None
    first, last = match.groups()
    if first == "" and last == "":
        raise RangeNotSatisfiable()
    if first == "":
        length = int(last)
        if length == 0:
            raise RangeNotSatisfiable()
        start, end = max(0, size - length), size - 1
    else:
        start = int(first)
        end = int(last) if last else size - 1
        end = min(end, size - 1)
    if start >= size or start > end:
        raise RangeNotSatisfiable()
    return start, end


def _content_type(name):
    suffix = Path(name).suffix.lower()
    if suffix not in CONTENT_TYPES:
        raise RecordingUnavailable("این نوع فایل به‌عنوان ضبط مکالمه پذیرفته نمی‌شود.")
    return CONTENT_TYPES[suffix]


def _local_candidates(base, reference, started_at):
    reference = reference.replace("\\", "/").lstrip("/")
    if "/" in reference:
        yield base / reference
        return
    if started_at is not None:
        local = timezone.localtime(started_at)
        yield base / f"{local:%Y}" / f"{local:%m}" / f"{local:%d}" / reference
    yield base / reference


def resolve_local(config, reference, started_at=None):
    """The recording's path inside the mounted root, or `RecordingUnavailable`."""
    root = config.get("recordings_path") or ""
    if not root:
        raise RecordingUnavailable("مسیر ضبط مکالمه تنظیم نشده است.")
    base = Path(root).resolve()
    _content_type(reference)
    for candidate in _local_candidates(base, reference, started_at):
        resolved = candidate.resolve()
        if not resolved.is_relative_to(base):
            raise RecordingUnavailable("مسیر فایل ضبط مکالمه نامعتبر است.")
        if resolved.is_file():
            return resolved
    raise RecordingUnavailable("فایل ضبط این مکالمه پیدا نشد.")


def _file_iterator(path, start, length):
    with open(path, "rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def stream_local(path, range_header):
    size = path.stat().st_size
    content_type = _content_type(path.name)
    try:
        window = parse_range(range_header, size)
    except RangeNotSatisfiable:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response
    start, end = window if window else (0, size - 1)
    length = end - start + 1 if size else 0
    response = StreamingHttpResponse(_file_iterator(path, start, length), content_type=content_type,
                                     status=206 if window else 200)
    response["Content-Length"] = str(length)
    response["Accept-Ranges"] = "bytes"
    if window:
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
    return response


def stream_url(config, secrets, reference, range_header):
    base = (config.get("recordings_base_url") or "").rstrip("/")
    if not base.startswith("https://"):
        raise RecordingUnavailable("نشانی سرویس ضبط مکالمه تنظیم نشده یا https نیست.")
    _content_type(reference)
    path = "/".join(quote(part) for part in reference.replace("\\", "/").split("/") if part not in ("", ".", ".."))
    url = f"{base}/{path}"
    if urlsplit(url).netloc != urlsplit(base).netloc:
        raise RecordingUnavailable("مسیر فایل ضبط مکالمه نامعتبر است.")
    headers = {"User-Agent": "Dolphin-Recordings/1"}
    if range_header:
        headers["Range"] = range_header
    username, password = config.get("recordings_username") or "", secrets.get("recordings_password") or ""
    if username:
        import base64

        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        upstream = urllib.request.urlopen(request, timeout=URL_TIMEOUT)  # noqa: S310 — https, configured host only
    except urllib.error.HTTPError as error:
        if error.code == 416:
            return HttpResponse(status=416)
        raise RecordingUnavailable("سرویس ضبط مکالمه فایل را نداد.") from error
    except (urllib.error.URLError, OSError) as error:
        raise RecordingUnavailable("سرویس ضبط مکالمه در دسترس نیست.") from error

    def body():
        try:
            while True:
                chunk = upstream.read(CHUNK)
                if not chunk:
                    break
                yield chunk
        finally:
            upstream.close()

    response = StreamingHttpResponse(body(), status=upstream.status, content_type=_content_type(reference))
    for header in ("Content-Length", "Content-Range"):
        if upstream.headers.get(header):
            response[header] = upstream.headers[header]
    response["Accept-Ranges"] = "bytes"
    return response


def recording_response(integration, config, secrets, call, range_header):
    if not call.recording:
        raise RecordingUnavailable("برای این مکالمه ضبطی ثبت نشده است.")
    mode = config.get("recordings_mode") or "none"
    if mode == "mount":
        return stream_local(resolve_local(config, call.recording, call.started_at), range_header)
    if mode == "url":
        return stream_url(config, secrets, call.recording, range_header)
    raise RecordingUnavailable("دسترسی به ضبط مکالمه برای این مرکز تلفن تنظیم نشده است.")
