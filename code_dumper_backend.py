#!/usr/bin/env python3
"""
Create a compact, backend-focused context bundle for Codex.

This script is designed for large frontend/admin-template repositories where
feeding every HTML page, vendor plugin, bundle, image, and demo file to an LLM
would waste a large amount of context.

Default usage (run from the project root):

    python code_dumper_backend.py

Useful examples:

    # Include the core CRM features only (default)
    python code_dumper_backend.py --features crm,auth,billing,support,calendar,api

    # Also include ecommerce, chat/inbox, and file-manager screens
    python code_dumper_backend.py --features all-business

    # Keep complete HTML instead of extracting backend-relevant contracts
    python code_dumper_backend.py --html-mode full

    # Disable the approximate token cap
    python code_dumper_backend.py --max-tokens 0

Outputs:
    codex_backend_context.txt   -> selected files/HTML contracts in one file
    codex_backend_excluded.txt  -> what was omitted and why

No third-party Python packages are required.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import html
import math
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence


DEFAULT_OUTPUT = "codex_backend_context.txt"
DEFAULT_REPORT = "codex_backend_excluded.txt"
DEFAULT_FEATURES = "crm,auth,billing,support,calendar,api"
DEFAULT_MAX_TOKENS = 120_000
DEFAULT_MAX_FILE_KB = 1_500

# Dependencies, generated output, caches, and IDE metadata.
GLOBAL_EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".next",
    ".nuxt",
    ".turbo",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "bower_components",
    "vendor",
    "venv",
    ".venv",
    "env",
    ".envdir",
    "dist",
    "build",
    "coverage",
    "htmlcov",
    "target",
    "tmp",
    "temp",
    "logs",
}

# Large theme/demo areas in the supplied Kariz-CRM structure. These are not
# backend contracts and are intentionally pruned before individual file scans.
THEME_PRUNED_PREFIXES = (
    "assets/css/",
    "assets/media/",
    "assets/plugins/",
    "src/media/",
    "src/plugins/",
    "src/sass/",
    "src/js/components/",
    "src/js/layout/",
    "src/js/vendors/",
    "src/js/widgets/",
    "asides/",
    "dashboards/",
    "layouts/",
    "pages/",
    "toolbars/",
    "widgets/",
    "utilities/",
)

BINARY_OR_ASSET_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".svg",
    ".bmp",
    ".tif",
    ".tiff",
    ".avif",
    ".mp3",
    ".wav",
    ".ogg",
    ".mp4",
    ".mov",
    ".avi",
    ".webm",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".class",
    ".pyc",
    ".pyo",
    ".wasm",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".ttf",
    ".otf",
    ".eot",
    ".woff",
    ".woff2",
    ".map",
}

STYLE_EXTENSIONS = {".css", ".scss", ".sass", ".less", ".styl"}
LOCK_FILES = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "poetry.lock",
    "pdm.lock",
    "Pipfile.lock",
    "composer.lock",
    "Gemfile.lock",
    "Cargo.lock",
    "go.sum",
}

SECRET_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.test",
    "credentials.json",
    "service-account.json",
    "secrets.json",
    "secrets.yml",
    "secrets.yaml",
}
SECRET_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}

MINIFIED_OR_BUNDLE_PATTERNS = (
    "*.min.js",
    "*.bundle.js",
    "*.min.css",
    "*.bundle.css",
    "*.chunk.js",
)

# Project specifications and dependency/config files are useful even when no
# backend has been written yet. README files are included deliberately; the
# original script excluded every Markdown file, which can hide requirements.
IMPORTANT_PROJECT_PATTERNS = (
    "README",
    "README.*",
    "BACKEND_SPEC.md",
    "BACKEND_REQUIREMENTS.md",
    "API_SPEC.md",
    "ARCHITECTURE.md",
    "requirements.txt",
    "requirements-*.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Pipfile",
    "package.json",
    "tsconfig.json",
    "jsconfig.json",
    "composer.json",
    "Gemfile",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Dockerfile",
    "Dockerfile.*",
    "docker-compose.yml",
    "docker-compose.yaml",
    "docker-compose.*.yml",
    "docker-compose.*.yaml",
    "Makefile",
    ".env.example",
    ".env.sample",
    ".env.template",
    "openapi.json",
    "openapi.yaml",
    "openapi.yml",
    "swagger.json",
    "swagger.yaml",
    "swagger.yml",
    "schema.prisma",
    "alembic.ini",
    "manage.py",
    "app.py",
    "main.py",
    "server.py",
    "config.py",
    "wsgi.py",
    "asgi.py",
    "urls.py",
    "src/main.ts",
    "src/server.ts",
    "src/index.ts",
    "src/app.ts",
    "src/app.module.ts",
    "schema.graphql",
    "schema.gql",
    "*postman*.json",
    "drizzle.config.*",
    "knexfile.*",
    "ormconfig.*",
)

SPEC_DOCUMENT_PATTERNS = (
    "docs/*backend*.md",
    "docs/*api*.md",
    "docs/*architecture*.md",
    "docs/*requirement*.md",
    "docs/*database*.md",
    "docs/*schema*.md",
    "specs/**/*.md",
    "spec/**/*.md",
)

BACKEND_ROOT_PREFIXES = (
    "app/",
    "backend/",
    "server/",
    "api/",
    "database/",
    "migrations/",
    "prisma/",
    "src/backend/",
    "src/server/",
    "src/api/",
)
BACKEND_PATH_SEGMENTS = {
    "routes",
    "routers",
    "controllers",
    "handlers",
    "services",
    "models",
    "schemas",
    "serializers",
    "repositories",
    "entities",
    "migrations",
    "database",
    "middleware",
    "middlewares",
    "permissions",
    "policies",
    "validators",
    "jobs",
    "workers",
    "tasks",
    "tests",
    "test",
}
BACKEND_SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".php",
    ".rb",
    ".cs",
    ".sql",
    ".prisma",
    ".graphql",
    ".gql",
    ".proto",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".xml",
    ".sh",
    ".md",
    ".txt",
}

BACKEND_SOURCE_FILENAMES = {
    "models.py",
    "views.py",
    "urls.py",
    "serializers.py",
    "admin.py",
    "apps.py",
    "tasks.py",
    "permissions.py",
    "schemas.py",
    "routers.py",
    "routes.py",
    "controllers.py",
    "services.py",
    "middleware.py",
    "server.js",
    "server.ts",
    "routes.js",
    "routes.ts",
}
BACKEND_SOURCE_NAME_PATTERNS = (
    "*.controller.ts",
    "*.service.ts",
    "*.module.ts",
    "*.entity.ts",
    "*.dto.ts",
    "*.schema.ts",
    "*.guard.ts",
    "*.strategy.ts",
    "*.resolver.ts",
    "*Controller.java",
    "*Service.java",
    "*Repository.java",
    "*Entity.java",
)

# Default feature set for the supplied static CRM template. The source files
# under src/js/custom are preferred over duplicate built copies under assets.
FEATURE_PATTERNS: Mapping[str, tuple[str, ...]] = {
    "crm": (
        "index.html",
        "apps/contacts/add-contact.html",
        "apps/contacts/edit-contact.html",
        "apps/contacts/view-contact.html",
        "apps/customers/list.html",
        "apps/customers/view.html",
        "apps/projects/activity.html",
        "apps/projects/budget.html",
        "apps/projects/files.html",
        "apps/projects/list.html",
        "apps/projects/project.html",
        "apps/projects/settings.html",
        "apps/projects/targets.html",
        "apps/projects/users.html",
        "apps/user-management/permissions.html",
        "apps/user-management/roles/list.html",
        "apps/user-management/roles/view.html",
        "apps/user-management/users/list.html",
        "apps/user-management/users/view.html",
        "src/js/custom/apps/contacts/**",
        "src/js/custom/apps/customers/**",
        "src/js/custom/apps/projects/**",
        "src/js/custom/apps/user-management/**",
        "src/js/custom/utilities/modals/create-project/**",
        "src/js/custom/utilities/modals/users-search.js",
    ),
    "auth": (
        "account/activity.html",
        "account/logs.html",
        "account/overview.html",
        "account/security.html",
        "account/settings.html",
        # One visual auth layout is enough; the other layouts are duplicates.
        "authentication/layouts/corporate/new-password.html",
        "authentication/layouts/corporate/reset-password.html",
        "authentication/layouts/corporate/sign-in.html",
        "authentication/layouts/corporate/sign-up.html",
        "authentication/layouts/corporate/two-factor.html",
        "authentication/general/account-deactivated.html",
        "authentication/general/password-confirmation.html",
        "authentication/general/verify-email.html",
        "src/js/custom/authentication/reset-password/new-password.js",
        "src/js/custom/authentication/reset-password/reset-password.js",
        "src/js/custom/authentication/sign-in/general.js",
        "src/js/custom/authentication/sign-in/two-factor.js",
        "src/js/custom/authentication/sign-up/general.js",
        "src/js/custom/account/security/**",
        "src/js/custom/account/settings/**",
        "src/js/custom/utilities/modals/two-factor-authentication.js",
    ),
    "billing": (
        "account/billing.html",
        "account/statements.html",
        "apps/invoices/create.html",
        # One canonical invoice representation is enough for a backend contract.
        "apps/invoices/view/invoice-1.html",
        "apps/subscriptions/add.html",
        "apps/subscriptions/list.html",
        "apps/subscriptions/view.html",
        "src/js/custom/account/billing/**",
        "src/js/custom/account/orders/**",
        "src/js/custom/apps/invoices/**",
        "src/js/custom/apps/subscriptions/**",
        "src/js/custom/utilities/modals/new-card.js",
    ),
    "api": (
        "account/api-keys.html",
        "src/js/custom/account/api-keys/**",
        "src/js/custom/utilities/modals/create-api-key.js",
    ),
    "support": (
        "apps/support-center/tickets/list.html",
        "apps/support-center/tickets/view.html",
        "src/js/custom/apps/support-center/tickets/**",
    ),
    "calendar": (
        "apps/calendar.html",
        "src/js/custom/apps/calendar/**",
    ),
    "ecommerce": (
        "apps/ecommerce/**",
        "src/js/custom/apps/ecommerce/**",
        "src/js/custom/utilities/modals/new-address.js",
        "src/js/custom/utilities/modals/new-card.js",
    ),
    "communication": (
        "apps/chat/**",
        "apps/inbox/**",
        "src/js/custom/apps/chat/**",
        "src/js/custom/apps/inbox/**",
    ),
    "files": (
        "apps/file-manager/files.html",
        "apps/file-manager/folders.html",
        "apps/file-manager/settings.html",
        "src/js/custom/apps/file-manager/**",
    ),
    "referrals": (
        "account/referrals.html",
        "src/js/custom/account/referrals/**",
    ),
}

ALL_BUSINESS_FEATURES = tuple(FEATURE_PATTERNS.keys())


@dataclass(frozen=True)
class SelectedFile:
    path: Path
    relative: str
    reason: str
    priority: int
    mode: str


@dataclass
class ScanResult:
    selected: list[SelectedFile]
    skipped: dict[str, list[str]]
    pruned_directories: dict[str, list[str]]


@dataclass
class FormContract:
    attrs: dict[str, str]
    fields: list[dict[str, str]]
    labels: list[dict[str, str]]
    buttons: list[dict[str, str]]
    options: list[dict[str, str]]


class HTMLContractParser(HTMLParser):
    """Extract backend-relevant contracts from a large static HTML page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.headings: list[str] = []
        self.forms: list[FormContract] = []
        self.tables: list[dict[str, object]] = []
        self.modals: list[str] = []
        self.links: list[dict[str, str]] = []
        self.standalone_fields: list[dict[str, str]] = []
        self.standalone_buttons: list[dict[str, str]] = []
        self.inline_scripts: list[str] = []

        self._capture_kind: str | None = None
        self._capture_buffer: list[str] = []
        self._capture_meta: dict[str, str] = {}
        self._current_form: FormContract | None = None
        self._current_table: dict[str, object] | None = None
        self._current_select: dict[str, str] | None = None
        self._in_inline_script = False
        self._inline_script_buffer: list[str] = []

    @staticmethod
    def _attrs(attrs: Sequence[tuple[str, str | None]]) -> dict[str, str]:
        return {key.lower(): (value or "") for key, value in attrs}

    @staticmethod
    def _useful_attrs(attrs: Mapping[str, str], *, for_control: bool = False) -> dict[str, str]:
        useful_names = {
            "id",
            "name",
            "type",
            "action",
            "method",
            "href",
            "value",
            "placeholder",
            "required",
            "checked",
            "selected",
            "multiple",
            "autocomplete",
            "min",
            "max",
            "step",
            "pattern",
            "for",
            "role",
        }
        result: dict[str, str] = {}
        for key, value in attrs.items():
            if key in useful_names:
                result[key] = value if value else "true"
            elif key.startswith("data-") and any(
                marker in key
                for marker in ("url", "route", "endpoint", "action", "method", "target", "status")
            ):
                result[key] = value
            elif for_control and key == "aria-label":
                result[key] = value
        return result

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(value)).strip()

    def _start_capture(self, kind: str, meta: Mapping[str, str] | None = None) -> None:
        self._capture_kind = kind
        self._capture_buffer = []
        self._capture_meta = dict(meta or {})

    def _finish_capture(self) -> tuple[str | None, str, dict[str, str]]:
        kind = self._capture_kind
        text = self._clean_text(" ".join(self._capture_buffer))
        meta = self._capture_meta
        self._capture_kind = None
        self._capture_buffer = []
        self._capture_meta = {}
        return kind, text, meta

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs = self._attrs(attrs_list)

        classes = set(attrs.get("class", "").split())
        if "modal" in classes and attrs.get("id"):
            self.modals.append(attrs["id"])

        if tag == "title":
            self._start_capture("title")
            return
        if tag in {"h1", "h2", "h3"}:
            self._start_capture("heading")
            return

        if tag == "form":
            self._current_form = FormContract(
                attrs=self._useful_attrs(attrs),
                fields=[],
                labels=[],
                buttons=[],
                options=[],
            )
            return

        if tag in {"input", "textarea", "select"}:
            control = {"tag": tag, **self._useful_attrs(attrs, for_control=True)}
            if self._current_form is not None:
                self._current_form.fields.append(control)
            else:
                self.standalone_fields.append(control)
            if tag == "select":
                self._current_select = control
            return

        if tag == "label":
            self._start_capture("label", self._useful_attrs(attrs))
            return

        if tag == "button":
            self._start_capture("button", self._useful_attrs(attrs, for_control=True))
            return

        if tag == "option" and self._current_select is not None:
            meta = self._useful_attrs(attrs)
            if self._current_select.get("name"):
                meta["select_name"] = self._current_select["name"]
            if self._current_select.get("id"):
                meta["select_id"] = self._current_select["id"]
            self._start_capture("option", meta)
            return

        if tag == "table":
            self._current_table = {
                "attrs": self._useful_attrs(attrs),
                "headers": [],
            }
            return

        if tag == "th" and self._current_table is not None:
            self._start_capture("table_header")
            return

        if tag == "a":
            href = attrs.get("href", "").strip()
            if href and (
                href.endswith(".html")
                or href.startswith("/api/")
                or href.startswith("api/")
                or "endpoint" in attrs
                or "route" in attrs
            ):
                link_attrs = self._useful_attrs(attrs)
                if len(self.links) < 120 and link_attrs not in self.links:
                    self.links.append(link_attrs)
            return

        if tag == "script" and not attrs.get("src"):
            script_type = attrs.get("type", "").lower()
            if script_type not in {"application/ld+json"}:
                self._in_inline_script = True
                self._inline_script_buffer = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag == "form" and self._current_form is not None:
            self.forms.append(self._current_form)
            self._current_form = None
            self._current_select = None
            return

        if tag == "select":
            self._current_select = None
            return

        if tag == "table" and self._current_table is not None:
            self.tables.append(self._current_table)
            self._current_table = None
            return

        if tag == "script" and self._in_inline_script:
            script = "".join(self._inline_script_buffer).strip()
            if script and len(script) <= 20_000:
                self.inline_scripts.append(script)
            self._in_inline_script = False
            self._inline_script_buffer = []
            return

        expected = {
            "title": "title",
            "h1": "heading",
            "h2": "heading",
            "h3": "heading",
            "label": "label",
            "button": "button",
            "option": "option",
            "th": "table_header",
        }.get(tag)

        if expected and self._capture_kind == expected:
            kind, text, meta = self._finish_capture()
            if kind == "title" and text:
                self.title = text
            elif kind == "heading" and text and text not in self.headings:
                if len(self.headings) < 40:
                    self.headings.append(text)
            elif kind == "label" and text:
                item = {**meta, "text": text}
                if self._current_form is not None:
                    self._current_form.labels.append(item)
            elif kind == "button":
                item = {**meta}
                if text:
                    item["text"] = text
                if self._current_form is not None:
                    self._current_form.buttons.append(item)
                elif item:
                    self.standalone_buttons.append(item)
            elif kind == "option":
                item = {**meta}
                if text:
                    item["text"] = text
                if self._current_form is not None:
                    self._current_form.options.append(item)
            elif kind == "table_header" and text and self._current_table is not None:
                headers = self._current_table["headers"]
                if isinstance(headers, list) and text not in headers and len(headers) < 80:
                    headers.append(text)

    def handle_data(self, data: str) -> None:
        if self._in_inline_script:
            self._inline_script_buffer.append(data)
        elif self._capture_kind is not None:
            self._capture_buffer.append(data)


class ContextDumper:
    def __init__(
        self,
        root: Path,
        output: Path,
        report: Path,
        features: Sequence[str],
        html_mode: str,
        max_tokens: int,
        max_file_kb: int,
    ) -> None:
        self.root = root.resolve()
        self.output = output.resolve()
        self.report = report.resolve()
        self.features = tuple(features)
        self.html_mode = html_mode
        self.max_tokens = max_tokens
        self.max_file_bytes = max_file_kb * 1024
        self.dynamic_skip_paths = {self.output, self.report}
        try:
            self.dynamic_skip_paths.add(Path(__file__).resolve())
        except NameError:
            pass

    @staticmethod
    def normalize(relative: Path | str) -> str:
        normalized = PurePosixPath(str(relative).replace("\\", "/")).as_posix()
        return normalized[2:] if normalized.startswith("./") else normalized

    @staticmethod
    def matches(path: str, pattern: str) -> bool:
        # Handle the very common "prefix/**" form explicitly and predictably.
        if pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            return path == prefix or path.startswith(prefix + "/")
        return fnmatch.fnmatchcase(path, pattern)

    def selected_feature(self, path: str) -> str | None:
        for feature in self.features:
            for pattern in FEATURE_PATTERNS[feature]:
                if self.matches(path, pattern):
                    return feature
        return None

    @staticmethod
    def is_secret_path(path: Path) -> bool:
        name_lower = path.name.lower()
        if name_lower in {name.lower() for name in SECRET_FILE_NAMES}:
            return True
        if path.suffix.lower() in SECRET_EXTENSIONS:
            return True
        if name_lower.startswith(".env.") and not any(
            marker in name_lower for marker in ("example", "sample", "template")
        ):
            return True
        return False

    @staticmethod
    def is_minified_or_bundle(path: str) -> bool:
        name = PurePosixPath(path).name
        return any(fnmatch.fnmatchcase(name, pattern) for pattern in MINIFIED_OR_BUNDLE_PATTERNS)

    @staticmethod
    def is_important_project_file(path: str) -> bool:
        name = PurePosixPath(path).name
        return any(
            fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(name, pattern)
            for pattern in IMPORTANT_PROJECT_PATTERNS
        ) or any(fnmatch.fnmatchcase(path, pattern) for pattern in SPEC_DOCUMENT_PATTERNS)

    @staticmethod
    def is_backend_source(path: str, suffix: str) -> bool:
        if suffix.lower() not in BACKEND_SOURCE_EXTENSIONS:
            return False
        if any(path.startswith(prefix) for prefix in BACKEND_ROOT_PREFIXES):
            return True
        pure_path = PurePosixPath(path)
        parts = set(pure_path.parts)
        if parts & BACKEND_PATH_SEGMENTS:
            return True
        if pure_path.name in BACKEND_SOURCE_FILENAMES:
            return True
        return any(fnmatch.fnmatchcase(pure_path.name, pattern) for pattern in BACKEND_SOURCE_NAME_PATTERNS)

    def source_duplicate_exists(self, path: str, known_paths: set[str]) -> bool:
        if not path.startswith("assets/js/custom/"):
            return False
        source_path = "src/js/custom/" + path.removeprefix("assets/js/custom/")
        return source_path in known_paths

    def map_assets_custom_to_source_pattern(self, path: str) -> str:
        if path.startswith("assets/js/custom/"):
            return "src/js/custom/" + path.removeprefix("assets/js/custom/")
        return path

    def prune_reason_for_dir(self, relative_dir: str, name: str) -> str | None:
        if name in GLOBAL_EXCLUDED_DIR_NAMES:
            return "dependency/cache/build directory"
        normalized = relative_dir.rstrip("/") + "/"
        if any(normalized.startswith(prefix) for prefix in THEME_PRUNED_PREFIXES):
            return "theme assets, vendor plugins, styles, or demo-only directory"
        return None

    def collect_paths(self) -> tuple[list[Path], dict[str, list[str]]]:
        files: list[Path] = []
        pruned: dict[str, list[str]] = defaultdict(list)

        for current_root, dirs, filenames in os.walk(self.root):
            current = Path(current_root)
            kept_dirs: list[str] = []
            for directory in dirs:
                child = current / directory
                relative = self.normalize(child.relative_to(self.root))
                reason = self.prune_reason_for_dir(relative, directory)
                if reason:
                    pruned[reason].append(relative + "/")
                else:
                    kept_dirs.append(directory)
            dirs[:] = kept_dirs

            for filename in filenames:
                path = current / filename
                if path.resolve() in self.dynamic_skip_paths:
                    continue
                files.append(path)

        return files, dict(pruned)

    def classify(self) -> ScanResult:
        all_paths, pruned = self.collect_paths()
        known_paths = {self.normalize(path.relative_to(self.root)) for path in all_paths}
        selected: list[SelectedFile] = []
        skipped: dict[str, list[str]] = defaultdict(list)

        for path in all_paths:
            relative = self.normalize(path.relative_to(self.root))
            suffix = path.suffix.lower()
            name = path.name

            if self.is_secret_path(path):
                skipped["secret or credential file (never send to Codex)"].append(relative)
                continue
            if name in LOCK_FILES:
                skipped["lockfile; useful for reproducibility, not for backend design"].append(relative)
                continue
            if suffix in BINARY_OR_ASSET_EXTENSIONS:
                skipped["binary/media/font/archive/database/source-map file"].append(relative)
                continue
            if suffix in STYLE_EXTENSIONS:
                skipped["CSS/Sass/Less styling; no backend contract"].append(relative)
                continue
            if self.is_minified_or_bundle(relative):
                skipped["minified or bundled generated code"].append(relative)
                continue
            if self.source_duplicate_exists(relative, known_paths):
                skipped["built duplicate; src/js/custom version is preferred"].append(relative)
                continue

            try:
                size = path.stat().st_size
            except OSError as exc:
                skipped[f"unreadable file: {exc.__class__.__name__}"].append(relative)
                continue
            if size > self.max_file_bytes:
                skipped[
                    f"larger than --max-file-kb ({self.max_file_bytes // 1024} KB)"
                ].append(relative)
                continue

            if self.is_important_project_file(relative):
                selected.append(
                    SelectedFile(path, relative, "project specification/configuration", 10, "full")
                )
                continue

            if self.is_backend_source(relative, suffix):
                mode = "contract" if suffix in {".html", ".htm"} and self.html_mode == "contract" else "full"
                selected.append(
                    SelectedFile(path, relative, "existing backend/API/schema/test source", 20, mode)
                )
                continue

            feature = self.selected_feature(relative)
            if feature:
                mode = "contract" if suffix in {".html", ".htm"} and self.html_mode == "contract" else "full"
                selected.append(
                    SelectedFile(path, relative, f"frontend contract for feature: {feature}", 30 if suffix not in {".html", ".htm"} else 40, mode)
                )
                continue

            # If the unbuilt source is missing, a non-minified assets/js/custom file
            # can serve as a fallback and is matched against source patterns.
            mapped = self.map_assets_custom_to_source_pattern(relative)
            feature = self.selected_feature(mapped)
            if feature and relative.startswith("assets/js/custom/"):
                selected.append(
                    SelectedFile(
                        path,
                        relative,
                        f"fallback custom JS for feature: {feature} (source copy not found)",
                        35,
                        "full",
                    )
                )
                continue

            skipped["outside selected backend/business context"].append(relative)

        selected.sort(key=lambda item: (item.priority, item.relative.lower()))
        return ScanResult(selected=selected, skipped=dict(skipped), pruned_directories=pruned)

    @staticmethod
    def read_text(path: Path) -> str:
        raw = path.read_bytes()
        if b"\x00" in raw[:8192]:
            raise ValueError("binary data detected")
        for encoding in ("utf-8", "utf-8-sig"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                pass
        return raw.decode("utf-8", errors="replace")

    @staticmethod
    def estimate_tokens_from_chars(char_count: int) -> int:
        # Approximation only. Source code and Persian/Unicode can tokenize
        # differently, but chars/4 is useful as a budget guardrail.
        return math.ceil(char_count / 4)

    @staticmethod
    def format_attrs(attrs: Mapping[str, str]) -> str:
        if not attrs:
            return "(none)"
        return ", ".join(f"{key}={value!r}" for key, value in attrs.items())

    def html_contract(self, content: str) -> str:
        parser = HTMLContractParser()
        parser.feed(content)
        parser.close()

        lines: list[str] = [
            "[COMPACT HTML BACKEND CONTRACT]",
            "The repeated visual/layout markup was intentionally omitted.",
        ]
        if parser.title:
            lines.append(f"Title: {parser.title}")
        if parser.headings:
            lines.append("Headings:")
            lines.extend(f"  - {heading}" for heading in parser.headings)

        if parser.forms:
            lines.append("Forms:")
            for index, form in enumerate(parser.forms, 1):
                lines.append(f"  Form {index}: {self.format_attrs(form.attrs)}")
                if form.labels:
                    lines.append("    Labels:")
                    for label in form.labels[:100]:
                        lines.append(f"      - {self.format_attrs(label)}")
                if form.fields:
                    lines.append("    Fields:")
                    for field in form.fields[:160]:
                        lines.append(f"      - {self.format_attrs(field)}")
                if form.options:
                    lines.append("    Select options:")
                    for option in form.options[:160]:
                        lines.append(f"      - {self.format_attrs(option)}")
                if form.buttons:
                    lines.append("    Buttons/actions:")
                    for button in form.buttons[:100]:
                        lines.append(f"      - {self.format_attrs(button)}")

        if parser.standalone_fields:
            lines.append("Standalone fields:")
            for field in parser.standalone_fields[:120]:
                lines.append(f"  - {self.format_attrs(field)}")

        if parser.standalone_buttons:
            lines.append("Standalone buttons/actions:")
            for button in parser.standalone_buttons[:120]:
                lines.append(f"  - {self.format_attrs(button)}")

        if parser.tables:
            lines.append("Tables:")
            for index, table in enumerate(parser.tables[:30], 1):
                attrs = table.get("attrs", {})
                headers = table.get("headers", [])
                lines.append(f"  Table {index}: {self.format_attrs(attrs if isinstance(attrs, dict) else {})}")
                if isinstance(headers, list) and headers:
                    lines.append("    Columns: " + " | ".join(str(item) for item in headers))

        if parser.modals:
            lines.append("Modal IDs: " + ", ".join(dict.fromkeys(parser.modals)))

        if parser.links:
            lines.append("Relevant page/API links:")
            for link in parser.links[:120]:
                lines.append(f"  - {self.format_attrs(link)}")

        if parser.inline_scripts:
            lines.append("Inline scripts:")
            for index, script in enumerate(parser.inline_scripts[:10], 1):
                lines.append(f"--- inline script {index} ---")
                lines.append(script)

        if len(lines) <= 2:
            lines.append("No forms, fields, tables, actions, or API-like links were found in this page.")

        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def render_tree(paths: Iterable[str]) -> str:
        tree: dict[str, dict] = {}
        for path in sorted(paths):
            node = tree
            parts = PurePosixPath(path).parts
            for part in parts:
                node = node.setdefault(part, {})

        lines: list[str] = []

        def walk(node: dict[str, dict], depth: int) -> None:
            for name in sorted(node, key=str.lower):
                child = node[name]
                suffix = "/" if child else ""
                lines.append("    " * depth + name + suffix)
                if child:
                    walk(child, depth + 1)

        walk(tree, 0)
        return "\n".join(lines)

    @staticmethod
    def sha256(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()

    def build_file_section(self, item: SelectedFile) -> str:
        content = self.read_text(item.path)
        rendered = self.html_contract(content) if item.mode == "contract" else content
        rendered = rendered.rstrip() + "\n"
        separator = "=" * 88
        return (
            f"\n{separator}\n"
            f"FILE: {item.relative}\n"
            f"WHY INCLUDED: {item.reason}\n"
            f"MODE: {item.mode}\n"
            f"SOURCE SHA256: {self.sha256(content)}\n"
            f"{separator}\n\n"
            f"{rendered}"
        )

    def write_outputs(self, result: ScanResult) -> tuple[int, int, int]:
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        selected_tree = self.render_tree(item.relative for item in result.selected)
        manifest = "\n".join(
            f"- [{item.priority:02d}] {item.relative} | {item.reason} | mode={item.mode}"
            for item in result.selected
        )

        header = f"""CODEX BACKEND CONTEXT
Generated: {generated_at}
Project root: {self.root}
Features: {', '.join(self.features)}
HTML mode: {self.html_mode}
Approximate token cap: {self.max_tokens if self.max_tokens else 'disabled'}

IMPORTANT LIMITATION
This bundle can show Codex the frontend contracts and any existing backend code,
but a static admin template does not define complete business rules. Before asking
Codex to implement production backend logic, add BACKEND_SPEC.md with entities,
relationships, roles/permissions, workflows, validation rules, status values,
API conventions, authentication method, and the chosen backend stack.

SELECTED PROJECT TREE
---------------------
{selected_tree or '(no files selected)'}

SELECTED FILE MANIFEST
----------------------
{manifest or '(no files selected)'}

FILE CONTENTS / CONTRACTS
-------------------------
"""

        sections: list[str] = [header]
        included_count = 0
        budget_skips: list[str] = []
        read_errors: list[str] = []
        current_chars = len(header)

        for item in result.selected:
            try:
                section = self.build_file_section(item)
            except Exception as exc:  # Keep one bad file from aborting the bundle.
                read_errors.append(f"{item.relative}: {exc}")
                continue

            projected_chars = current_chars + len(section)
            projected_tokens = self.estimate_tokens_from_chars(projected_chars)
            if self.max_tokens and projected_tokens > self.max_tokens:
                budget_skips.append(item.relative)
                continue

            sections.append(section)
            current_chars = projected_chars
            included_count += 1

        footer_lines = [
            "\n" + "#" * 88,
            "GENERATION SUMMARY",
            "#" * 88,
            f"Included files: {included_count}",
            f"Selected but omitted by token budget: {len(budget_skips)}",
            f"Read/parse errors: {len(read_errors)}",
        ]
        if budget_skips:
            footer_lines.append("Budget-omitted files:")
            footer_lines.extend(f"  - {path}" for path in budget_skips)
        if read_errors:
            footer_lines.append("Read/parse errors:")
            footer_lines.extend(f"  - {message}" for message in read_errors)
        footer = "\n".join(footer_lines) + "\n"
        sections.append(footer)

        final_text = "".join(sections)
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(final_text, encoding="utf-8")

        # Merge runtime omissions into the report without listing thousands of
        # nearly identical files in full.
        report_skipped = {key: list(value) for key, value in result.skipped.items()}
        if budget_skips:
            report_skipped["selected but over the approximate token budget"] = budget_skips
        if read_errors:
            report_skipped["read/parse error"] = read_errors

        self.write_report(report_skipped, result.pruned_directories, included_count)
        return included_count, len(final_text), self.estimate_tokens_from_chars(len(final_text))

    def write_report(
        self,
        skipped: Mapping[str, Sequence[str]],
        pruned: Mapping[str, Sequence[str]],
        included_count: int,
    ) -> None:
        lines = [
            "FILES/DIRECTORIES CODEX SHOULD NOT READ BY DEFAULT",
            "=" * 72,
            "",
            "Use codex_backend_context.txt as the primary context file.",
            "This report explains the omitted material and keeps the omission list auditable.",
            "",
            "Main rules:",
            "1. Never provide real .env files, credentials, private keys, or service-account files.",
            "2. Skip vendor dependencies, node_modules, generated bundles, minified files, and lockfiles.",
            "3. Skip images, fonts, media, PDFs, archives, compiled binaries, databases, and source maps.",
            "4. Skip CSS/Sass and generic UI component libraries when the task is backend implementation.",
            "5. Prefer src/js/custom over duplicate assets/js/custom output.",
            "6. Keep one canonical auth/invoice layout instead of every visual variation.",
            "7. Add optional feature groups only when that feature is actually in scope.",
            "",
            f"Included file count: {included_count}",
            "",
        ]

        for reason in sorted(pruned):
            values = sorted(set(pruned[reason]))
            lines.append(f"PRUNED DIRECTORIES — {reason} ({len(values)})")
            lines.extend(f"  - {value}" for value in values[:80])
            if len(values) > 80:
                lines.append(f"  ... and {len(values) - 80} more")
            lines.append("")

        for reason in sorted(skipped):
            values = sorted(set(skipped[reason]))
            lines.append(f"SKIPPED FILES — {reason} ({len(values)})")
            lines.extend(f"  - {value}" for value in values[:80])
            if len(values) > 80:
                lines.append(f"  ... and {len(values) - 80} more")
            lines.append("")

        self.report.parent.mkdir(parents=True, exist_ok=True)
        self.report.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_features(raw: str) -> tuple[str, ...]:
    values = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not values:
        raise ValueError("At least one feature must be selected.")
    if "all-business" in values or "all" in values:
        return ALL_BUSINESS_FEATURES

    unknown = sorted(set(values) - set(FEATURE_PATTERNS))
    if unknown:
        available = ", ".join(sorted(FEATURE_PATTERNS))
        raise ValueError(f"Unknown feature(s): {', '.join(unknown)}. Available: {available}")
    # Preserve user order while removing duplicates.
    return tuple(dict.fromkeys(values))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge only backend-relevant project files into a compact Codex context bundle."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root (default: current directory).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT),
        help=f"Context output path (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(DEFAULT_REPORT),
        help=f"Exclusion report path (default: {DEFAULT_REPORT}).",
    )
    parser.add_argument(
        "--features",
        default=DEFAULT_FEATURES,
        help=(
            "Comma-separated feature groups. Available: "
            + ", ".join(sorted(FEATURE_PATTERNS))
            + ", all-business."
        ),
    )
    parser.add_argument(
        "--html-mode",
        choices=("contract", "full"),
        default="contract",
        help="contract extracts fields/forms/tables/actions; full copies entire HTML (default: contract).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=(
            "Approximate output token cap using chars/4. Use 0 to disable "
            f"(default: {DEFAULT_MAX_TOKENS})."
        ),
    )
    parser.add_argument(
        "--max-file-kb",
        type=int,
        default=DEFAULT_MAX_FILE_KB,
        help=f"Skip individual files larger than this size (default: {DEFAULT_MAX_FILE_KB} KB).",
    )
    return parser


def resolve_output(root: Path, requested: Path) -> Path:
    return requested if requested.is_absolute() else root / requested


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    root = args.root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        parser.error(f"Project root does not exist or is not a directory: {root}")
    if args.max_tokens < 0:
        parser.error("--max-tokens cannot be negative")
    if args.max_file_kb <= 0:
        parser.error("--max-file-kb must be greater than zero")

    try:
        features = parse_features(args.features)
    except ValueError as exc:
        parser.error(str(exc))

    output = resolve_output(root, args.output.expanduser())
    report = resolve_output(root, args.report.expanduser())
    if output == report:
        parser.error("--output and --report must be different files")

    dumper = ContextDumper(
        root=root,
        output=output,
        report=report,
        features=features,
        html_mode=args.html_mode,
        max_tokens=args.max_tokens,
        max_file_kb=args.max_file_kb,
    )

    result = dumper.classify()
    included, char_count, token_estimate = dumper.write_outputs(result)

    print("Done.")
    print(f"Context file : {output}")
    print(f"Exclusion log: {report}")
    print(f"Included     : {included} files")
    print(f"Characters   : {char_count:,}")
    print(f"Approx tokens: {token_estimate:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
