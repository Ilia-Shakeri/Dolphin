import os
import re
import subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path(".").resolve()
OUTPUT = ROOT / "dolphin_review_bundle.txt"

# ---------------------------------------------------------
# Only first-party / operational files needed for review
# ---------------------------------------------------------

INCLUDE_ROOT_FILES = {
    "AGENTS.md",
    "BACKEND_SPEC.md",
    "DOLPHIN_PROJECT_HANDOFF.md",
    "DOLPHIN_CLIENT1_CODEX_ROADMAP.md",
    ".env.example",
    ".gitignore",
    ".dockerignore",
    "Dockerfile",
    "compose.yml",
    "compose.write-stop.yml",
    "compose.restore-verify.yml",
    "requirements.txt",
    "requirements-direct.txt",
    "manage.py",
}

INCLUDE_DIRS = {
    "accounts",
    "auditlog",
    "common",
    "config",
    "reports",
    "sales",
    "nginx",
    "scripts",
    "docs/backend",
    "docs/ops",
}

# Huge vendor/demo/archive areas that are not needed
EXCLUDE_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "vendor",
    "staticfiles",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",

    # Metronic/demo archive
    "assets",
    "src",
    "apps",
    "account",
    "authentication",
    "asides",
    "dashboards",
    "layouts",
    "pages",
    "toolbars",
    "utilities",
    "widgets",
}

EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".pdf",
    ".docx",
    ".xlsx",
    ".zip",
    ".tar",
    ".gz",
    ".pem",
    ".key",
    ".crt",
    ".cer",
    ".p12",
    ".pfx",
    ".map",
}

EXCLUDE_FILES = {
    OUTPUT.name,
    ".env",
    ".env.production",
    ".env.local",
    ".env.prod",
    "credentials.json",
    "service-account.json",
    ".pgpass",
    "pgpass.conf",
}

# Avoid dumping absurdly large generated/minified files
MAX_FILE_SIZE = 500_000  # 500 KB

TEXT_EXTENSIONS = {
    ".py",
    ".html",
    ".js",
    ".css",
    ".scss",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".txt",
    ".md",
    ".sql",
    ".sh",
    ".ps1",
}

# ---------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------

SECRET_PATTERN = re.compile(
    r"""(?ix)
    ^(\s*
    (?:SECRET_KEY|
       PASSWORD|
       DB_PASSWORD|
       DATABASE_PASSWORD|
       API_KEY|
       TOKEN|
       ACCESS_TOKEN|
       REFRESH_TOKEN|
       PRIVATE_KEY|
       CLIENT_SECRET|
       AWS_SECRET_ACCESS_KEY)
    \s*[:=]\s*)
    (.+)$
    """
)


def redact_line(line):
    match = SECRET_PATTERN.match(line)

    if match:
        return f"{match.group(1)}<REDACTED>\n"

    return line


# ---------------------------------------------------------
# Path selection
# ---------------------------------------------------------

def relative_path(path):
    return path.relative_to(ROOT).as_posix()


def is_inside_included_dir(rel):
    for allowed in INCLUDE_DIRS:
        if rel == allowed or rel.startswith(allowed + "/"):
            return True

    return False


def should_include(path):
    if not path.is_file():
        return False

    rel = relative_path(path)

    if path.name in EXCLUDE_FILES:
        return False

    parts = set(path.relative_to(ROOT).parts)

    if parts.intersection(EXCLUDE_DIRS):
        return False

    if path.suffix.lower() in EXCLUDE_EXTENSIONS:
        return False

    if path.stat().st_size > MAX_FILE_SIZE:
        return False

    # Explicit root files
    if "/" not in rel and path.name in INCLUDE_ROOT_FILES:
        return True

    # Everything inside approved first-party dirs
    if is_inside_included_dir(rel):
        if path.suffix.lower() in TEXT_EXTENSIONS:
            return True

        # Extensionless config/scripts
        if not path.suffix:
            return True

    return False


def collect_files():
    result = []

    for path in ROOT.rglob("*"):
        try:
            if should_include(path):
                result.append(path)
        except (OSError, PermissionError):
            continue

    return sorted(result, key=lambda p: relative_path(p).lower())


# ---------------------------------------------------------
# Project tree
# ---------------------------------------------------------

def generate_tree(files):
    lines = ["PROJECT REVIEW STRUCTURE", "=" * 80, ""]

    tree = {}

    for file in files:
        parts = file.relative_to(ROOT).parts
        node = tree

        for part in parts[:-1]:
            node = node.setdefault(part, {})

        node[parts[-1]] = None

    def render(node, level=0):
        for name in sorted(node, key=str.lower):
            value = node[name]
            indent = "    " * level

            if value is None:
                lines.append(f"{indent}{name}")
            else:
                lines.append(f"{indent}{name}/")
                render(value, level + 1)

    render(tree)

    return "\n".join(lines)


# ---------------------------------------------------------
# Safe command execution
# ---------------------------------------------------------

def run_command(title, command, timeout=180):
    output = []

    output.append("")
    output.append("=" * 80)
    output.append(f"CHECK: {title}")
    output.append(f"COMMAND: {' '.join(command)}")
    output.append("=" * 80)

    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env={
                **os.environ,
                "PYTHONUNBUFFERED": "1",
            },
        )

        output.append(f"EXIT_CODE: {proc.returncode}")
        output.append(proc.stdout or "<NO OUTPUT>")

    except FileNotFoundError:
        output.append("SKIPPED: executable not installed")

    except subprocess.TimeoutExpired as e:
        output.append("TIMEOUT")
        if e.stdout:
            output.append(str(e.stdout))

    except Exception as exc:
        output.append(f"ERROR: {type(exc).__name__}: {exc}")

    return "\n".join(output)


# ---------------------------------------------------------
# File dump
# ---------------------------------------------------------

def dump_file(path):
    rel = relative_path(path)

    output = [
        "",
        "#" * 100,
        f"FILE: {rel}",
        "#" * 100,
        "",
    ]

    try:
        with path.open(
            "r",
            encoding="utf-8",
            errors="replace",
        ) as f:
            for line_number, line in enumerate(f, 1):
                safe_line = redact_line(line)
                output.append(f"{line_number:05d} | {safe_line.rstrip()}")

    except Exception as exc:
        output.append(
            f"<FAILED TO READ: {type(exc).__name__}: {exc}>"
        )

    return "\n".join(output)


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    files = collect_files()

    print(f"Selected files: {len(files)}")
    print(f"Output: {OUTPUT}")

    with OUTPUT.open(
        "w",
        encoding="utf-8",
        errors="replace",
    ) as outfile:

        outfile.write("DOLPHIN CRM REVIEW BUNDLE\n")
        outfile.write(
            f"Generated: {datetime.now().isoformat(timespec='seconds')}\n"
        )
        outfile.write(f"Root: {ROOT.name}\n")
        outfile.write(f"Selected files: {len(files)}\n\n")

        # -------------------------------------------------
        # Git evidence
        # -------------------------------------------------

        outfile.write(
            run_command(
                "Git HEAD",
                ["git", "rev-parse", "HEAD"],
                timeout=15,
            )
        )

        outfile.write(
            run_command(
                "Git status",
                ["git", "status", "--short"],
                timeout=15,
            )
        )

        # -------------------------------------------------
        # Structure
        # -------------------------------------------------

        outfile.write("\n\n")
        outfile.write(generate_tree(files))
        outfile.write("\n\n")

        # -------------------------------------------------
        # File contents
        # -------------------------------------------------

        outfile.write("\n")
        outfile.write("=" * 100)
        outfile.write("\nFILE CONTENTS\n")
        outfile.write("=" * 100)
        outfile.write("\n")

        for path in files:
            outfile.write(dump_file(path))

        # -------------------------------------------------
        # Safe repository checks
        # -------------------------------------------------

        checks = [
            (
                "Django system check",
                [
                    "python",
                    "manage.py",
                    "check",
                    "--settings=config.test_settings",
                ],
                120,
            ),

            (
                "Migration drift",
                [
                    "python",
                    "manage.py",
                    "makemigrations",
                    "--check",
                    "--dry-run",
                    "--settings=config.test_settings",
                ],
                120,
            ),

            (
                "Full Django test suite",
                [
                    "python",
                    "manage.py",
                    "test",
                    "--settings=config.test_settings",
                    "-v",
                    "1",
                ],
                900,
            ),

            (
                "Python dependency consistency",
                [
                    "python",
                    "-m",
                    "pip",
                    "check",
                ],
                120,
            ),

            (
                "HTML branding guard",
                [
                    "python",
                    "scripts/check_html_branding.py",
                ],
                180,
            ),
        ]

        for title, command, timeout in checks:
            outfile.write(
                run_command(
                    title,
                    command,
                    timeout,
                )
            )

        # Docker config check: safe, no containers started
        outfile.write(
            run_command(
                "Docker Compose config",
                [
                    "docker",
                    "compose",
                    "config",
                    "--quiet",
                ],
                120,
            )
        )

        outfile.write(
            run_command(
                "Docker Compose write-stop config",
                [
                    "docker",
                    "compose",
                    "-f",
                    "compose.yml",
                    "-f",
                    "compose.write-stop.yml",
                    "config",
                    "--quiet",
                ],
                120,
            )
        )

        outfile.write("\n\nEND OF DOLPHIN REVIEW BUNDLE\n")

    size_mb = OUTPUT.stat().st_size / (1024 * 1024)

    print()
    print("DONE")
    print(f"Files included: {len(files)}")
    print(f"Bundle size: {size_mb:.2f} MB")
    print(f"Send me this file: {OUTPUT.name}")


if __name__ == "__main__":
    main()