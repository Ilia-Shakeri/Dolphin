"""Validate that the application image ships only runtime-necessary files.

Two independent modes, because they prove different things:

  --context
      Walks the repository and applies the `.dockerignore` rules to work out
      exactly which paths `COPY . .` would place into the image. Runs anywhere,
      needs no Docker. This proves the BUILD DEFINITION is correct. It does not
      prove anything about a real artifact.

  --listing FILE
      Reads a file listing captured from a real built image, e.g.

          docker run --rm --entrypoint sh IMAGE -c 'find /app -type f' > listing.txt

      and checks the actual shipped content. This proves the ARTIFACT is
      correct, and is the gate that release must use.

Both modes enforce the same two-sided contract:

  * DENY  - developer/ops/documentation material must not be present.
  * EXPECT- the handful of paths the runtime genuinely needs must be present,
            so that an over-aggressive `.dockerignore` cannot silently produce
            a broken image.

Exit status is 0 when the contract holds and 1 when it does not. Nothing is
mutated and no network or Docker call is made.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Paths that must never be inside the runtime image. Each entry is
# (label, dockerignore-style pattern).
DENY_PATTERNS: list[tuple[str, str]] = [
    ("git metadata", ".git"),
    ("environment file", ".env*"),
    ("internal documentation", "docs"),
    ("root planning/handoff document", "*.md"),
    ("test suite", "**/tests"),
    ("ops scripts", "scripts"),
    ("reverse-proxy config", "nginx"),
    ("compose definition", "compose*.yml"),
    ("unlocked dependency list", "requirements-direct.txt"),
    ("source map", "**/*.map"),
    ("code dumper", "code_dumper*.py"),
    ("private key", "**/*.pem"),
    ("private key", "**/*.key"),
    ("database dump", "**/*.sql.gz"),
    ("database file", "**/*.sqlite3"),
    ("editor metadata", ".vscode"),
    ("editor metadata", ".idea"),
    # Vendor/demo template tree - visual reference only, never served.
    # `assets` is NOT denied wholesale: the served UI is built on the purchased
    # theme, so the few bundles/fonts it loads must ship. The demo material
    # inside it is denied by path instead, and the runtime files it does need
    # are asserted in EXPECT_PRESENT below.
    ("theme demo imagery", "assets/media"),
    ("theme demo plugins", "assets/plugins/custom"),
    ("theme demo scripts", "assets/js/custom"),
    ("unused icon family", "assets/plugins/global/fonts/@fortawesome"),
    ("unused icon family", "assets/plugins/global/fonts/bootstrap-icons"),
    ("unused icon family", "assets/plugins/global/fonts/line-awesome"),
    ("unused LTR build", "assets/css/style.bundle.css"),
    ("unused LTR build", "assets/plugins/global/plugins.bundle.css"),
    ("unloaded bundle", "assets/plugins/global/plugins.bundle.js"),
    ("unloaded bundle", "assets/js/widgets.bundle.js"),
    ("vendor demo tree", "src"),
    ("vendor demo tree", "dashboards"),
    ("vendor demo tree", "pages"),
    ("vendor demo tree", "apps"),
    ("vendor demo tree", "layouts"),
    ("vendor demo tree", "toolbars"),
    ("vendor demo tree", "widgets"),
    ("vendor demo tree", "utilities"),
    ("vendor demo tree", "account"),
    ("vendor demo tree", "authentication"),
    ("vendor demo tree", "asides"),
    ("vendor demo page", "index.html"),
    ("vendor demo page", "landing.html"),
]

# Paths the runtime genuinely needs. Guards against over-exclusion.
EXPECT_PRESENT: list[str] = [
    "manage.py",
    "config/settings.py",
    "config/production_settings.py",
    "config/wsgi.py",
    "config/urls.py",
    "accounts/models.py",
    "sales/models.py",
    "common/ui_urls.py",
    "common/static/common/forooshbin-app.js",
    "common/static/common/forooshbin.css",
    "common/static/common/brand/favicon.ico",
    "common/templates/common/base.html",
    # The purchased theme's runtime. Without these the image builds and starts,
    # collectstatic reports success, and every page renders unstyled with a 404
    # for each bundle — which is exactly what happened before this list existed.
    "assets/css/style.bundle.rtl.css",
    "assets/plugins/global/plugins.bundle.rtl.css",
    "assets/js/scripts.bundle.js",
    "assets/fonts/IRANSansWeb.woff",
    "assets/fonts/IRANSansWeb.ttf",
    "assets/fonts/IRANSansWeb.eot",
    "assets/plugins/global/fonts/keenicons/keenicons-duotone.woff",
    "assets/plugins/global/fonts/keenicons/keenicons-outline.woff",
    "assets/plugins/global/fonts/keenicons/keenicons-solid.woff",
]


def pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate one .dockerignore pattern into an anchored regex.

    Supports the subset the repository actually uses: `*`, `?`, and `**`.
    `*` and `?` never cross a path separator; `**` spans whole directories.
    """
    segments = pattern.strip("/").split("/")
    out: list[str] = []
    for segment in segments:
        if segment == "**":
            # zero or more complete directory levels
            out.append("(?:[^/]+/)*")
            continue
        rendered = ""
        for char in segment:
            if char == "*":
                rendered += "[^/]*"
            elif char == "?":
                rendered += "[^/]"
            else:
                rendered += re.escape(char)
        out.append(rendered + "/")
    joined = "".join(out).rstrip("/")
    return re.compile(f"^{joined}$")


def path_matches(relative_path: str, compiled: re.Pattern[str]) -> bool:
    """True when the path, or any ancestor directory of it, matches.

    Docker excludes an entire subtree when a directory matches a pattern, so a
    file is covered if any of its parent prefixes matches too.
    """
    parts = relative_path.split("/")
    for index in range(1, len(parts) + 1):
        if compiled.match("/".join(parts[:index])):
            return True
    return False


def load_dockerignore(path: Path) -> list[tuple[bool, re.Pattern[str]]]:
    """Return (is_exception, regex) pairs in file order."""
    rules: list[tuple[bool, re.Pattern[str]]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        is_exception = line.startswith("!")
        if is_exception:
            line = line[1:].strip()
        if not line:
            continue
        rules.append((is_exception, pattern_to_regex(line)))
    return rules


def is_ignored(relative_path: str, rules: list[tuple[bool, re.Pattern[str]]]) -> bool:
    """Apply .dockerignore rules in order; the last match decides."""
    ignored = False
    for is_exception, compiled in rules:
        if path_matches(relative_path, compiled):
            ignored = not is_exception
    return ignored


def collect_context_paths() -> list[str]:
    """Simulate `COPY . .` and return the paths that would enter the image."""
    rules = load_dockerignore(REPO_ROOT / ".dockerignore")
    included: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        if not is_ignored(relative, rules):
            included.append(relative)
    return sorted(included)


def read_listing(listing_path: Path, strip_prefix: str) -> list[str]:
    """Normalise a `find`-style listing captured from a real image."""
    prefix = strip_prefix.rstrip("/") + "/"
    paths: list[str] = []
    for raw_line in listing_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().replace("\\", "/")
        if not line:
            continue
        if line.startswith(prefix):
            line = line[len(prefix) :]
        elif line == strip_prefix.rstrip("/"):
            continue
        paths.append(line.lstrip("./"))
    return sorted(paths)


def validate(paths: list[str], source: str, quiet: bool = False) -> int:
    """Return 0 when the content contract holds, 1 otherwise.

    `quiet` suppresses reporting so tests can assert on the status code without
    writing to the test runner's output.
    """
    violations: list[str] = []
    for label, pattern in DENY_PATTERNS:
        compiled = pattern_to_regex(pattern)
        hits = [candidate for candidate in paths if path_matches(candidate, compiled)]
        for hit in sorted(hits):
            violations.append(f"{label}: {hit}")

    present = set(paths)
    missing = [expected for expected in EXPECT_PRESENT if expected not in present]

    def report(message: str) -> None:
        if not quiet:
            print(message)

    report(f"IMAGE_CONTENT source={source} files={len(paths)}")

    if violations:
        report(f"FORBIDDEN CONTENT ({len(violations)}):")
        for violation in violations[:50]:
            report(f"  - {violation}")
        if len(violations) > 50:
            report(f"  ... and {len(violations) - 50} more")

    if missing:
        report(f"MISSING REQUIRED RUNTIME FILES ({len(missing)}):")
        for item in missing:
            report(f"  - {item}")

    if violations or missing:
        report("IMAGE_CONTENT_FAIL")
        return 1

    report("IMAGE_CONTENT_PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--context",
        action="store_true",
        help="simulate the build context from .dockerignore (no Docker needed)",
    )
    group.add_argument(
        "--listing",
        type=Path,
        help="path to a file listing captured from a real built image",
    )
    parser.add_argument(
        "--strip-prefix",
        default="/app",
        help="image path prefix to strip in --listing mode (default: /app)",
    )
    parser.add_argument(
        "--print-paths",
        action="store_true",
        help="print every included path before validating",
    )
    args = parser.parse_args()

    if args.context:
        paths = collect_context_paths()
        source = "build-context-simulation"
    else:
        if not args.listing.is_file():
            print(f"listing not found: {args.listing}")
            return 1
        paths = read_listing(args.listing, args.strip_prefix)
        source = f"image-listing:{args.listing.name}"

    if args.print_paths:
        for path in paths:
            print(f"  {path}")

    return validate(paths, source)


if __name__ == "__main__":
    sys.exit(main())
