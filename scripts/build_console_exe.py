#!/usr/bin/env python3
"""Freeze the deployment console into a single Windows `.exe`.

Product-owner request 2026-09-20: «قابلیت ساخت `.exe`». The console is an
operator tool — it signs manifests with a private key that must never be on
a customer host — and asking the person who runs it to install Python, clone
the repository and remember a command line is friction with no upside. One
file they double-click is the right shape for it.

**PyInstaller is an operator-only dependency.** It is not in
`requirements.txt` and never enters a shipped image; `scripts/` is excluded
from the build context entirely (`.dockerignore`). It is listed in
`scripts/requirements-console.txt` beside `pywebview`, and this script says
so and stops rather than installing anything itself — a build tool that
silently pip-installs is a build tool that can change what it builds.

    pip install -r scripts/requirements-console.txt
    python scripts/build_console_exe.py

The result is `dist/dolphin-console.exe`. It is **not** committed and not
released: it is built on the operator's own machine, from the checkout they
already trust, which is the whole point of a tool that holds a signing key.

**What has to be bundled.** The console imports `common.deployment.registry`
for the feature list and `common.deployment.pages` for the panel's routes —
and the second reaches the Django URL resolver, which means Django, the
settings module and every app package have to be inside the executable too.
`--collect-all` on the project packages is what does that; a frozen console
missing one of them would start and then show every feature as opening no
pages, which is exactly the silent-degradation this script exists to avoid.
So the build *verifies* the result rather than trusting it: it runs the
frozen binary once with `--self-check` and fails if the page list came back
empty.
"""

import argparse
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DIST = REPOSITORY_ROOT / "dist"
NAME = "dolphin-console"

#: Everything the console reaches at runtime that PyInstaller's import
#: analysis cannot see, because Django finds it by name at startup rather
#: than by an `import` statement this file could follow.
COLLECT = (
    "django",
    "rest_framework",
    "config",
    "common",
    "accounts",
    "sales",
    "billing",
    "inventory",
    "aftersales",
    "communications",
    "attachments",
    "auditlog",
    "chat",
    "reports",
)


def _require_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "PyInstaller is not installed.\n"
            "It is an operator-machine-only dependency and this script will not\n"
            "install it for you:\n\n"
            "    pip install -r scripts/requirements-console.txt\n",
            file=sys.stderr,
        )
        raise SystemExit(2)


def build(*, clean=False):
    _require_pyinstaller()
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        NAME,
        # No console window would hide the URL it prints and every error it
        # reports; this tool is driven from a terminal and should keep one.
        "--console",
        "--distpath",
        str(DIST),
        "--workpath",
        str(REPOSITORY_ROOT / "build" / "console"),
        "--specpath",
        str(REPOSITORY_ROOT / "build"),
        "--paths",
        str(REPOSITORY_ROOT),
    ]
    for package in COLLECT:
        command += ["--collect-all", package]
    if clean:
        command.append("--clean")
    command.append(str(REPOSITORY_ROOT / "scripts" / "manifest_builder.py"))

    print("$ " + " ".join(command))
    subprocess.run(command, check=True, cwd=REPOSITORY_ROOT)

    executable = DIST / (f"{NAME}.exe" if sys.platform == "win32" else NAME)
    if not executable.exists():
        raise SystemExit(f"PyInstaller reported success but {executable} is missing.")
    _verify(executable)
    print(f"\nBuilt {executable}")


def _verify(executable):
    """Run the frozen console once and make it prove it can see the panel.

    A binary that starts is not a binary that works: the failure mode this
    guards is a missing project package, which does not crash — it makes
    `common.deployment.pages` return nothing and every feature appear to
    open no pages at all. `--self-check` answers with the counts and exits.
    """
    print("\n$ %s --self-check" % executable)
    result = subprocess.run(
        [str(executable), "--self-check"], capture_output=True, text=True, timeout=180
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise SystemExit("the frozen console failed its own self-check")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true", help="discard PyInstaller's cache first")
    build(clean=parser.parse_args().clean)


if __name__ == "__main__":
    main()
