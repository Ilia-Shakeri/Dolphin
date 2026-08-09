from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import re

from django.test import SimpleTestCase
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
DIRECT_REQUIREMENTS = PROJECT_ROOT / "requirements-direct.txt"
DIRECT_PRODUCTION_PACKAGES = {
    "django",
    "djangorestframework",
    "drf-spectacular",
    "gunicorn",
    "openpyxl",
    "psycopg",
}


HASH_OPTION = re.compile(r"--hash=sha256:([a-f0-9]{64})")


def load_requirement_rows(path):
    rows = []
    pending = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        continued = line.endswith("\\")
        if continued:
            line = line[:-1].rstrip()
        pending = f"{pending} {line}".strip()
        if not continued:
            rows.append(pending)
            pending = ""
    if pending:
        raise AssertionError("Requirement continuation is incomplete.")
    return rows


def load_requirements(path):
    return [
        Requirement(row.split(" --hash=", 1)[0])
        for row in load_requirement_rows(path)
    ]


class DependencyContractTests(SimpleTestCase):
    def test_all_runtime_packages_have_reviewed_sha256_hashes(self):
        for row in load_requirement_rows(RUNTIME_REQUIREMENTS):
            hashes = HASH_OPTION.findall(row)
            self.assertTrue(hashes, row.split("==", 1)[0])
            self.assertEqual(len(hashes), len(set(hashes)))
            residue = HASH_OPTION.sub("", row)
            self.assertNotIn("--hash=", residue)

    def test_all_runtime_packages_have_one_exact_version(self):
        seen_names = set()
        for requirement in load_requirements(RUNTIME_REQUIREMENTS):
            name = canonicalize_name(requirement.name)
            self.assertNotIn(name, seen_names, f"{requirement.name} is duplicated")
            seen_names.add(name)
            specifiers = list(requirement.specifier)
            self.assertEqual(
                len(specifiers),
                1,
                f"{requirement.name} must have one exact version",
            )
            self.assertEqual(specifiers[0].operator, "==")
            self.assertNotIn("*", specifiers[0].version)

    def test_direct_production_packages_are_in_runtime_lock(self):
        locked_requirements = {
            canonicalize_name(requirement.name): requirement
            for requirement in load_requirements(RUNTIME_REQUIREMENTS)
        }
        direct_requirements = {
            canonicalize_name(requirement.name): requirement
            for requirement in load_requirements(DIRECT_REQUIREMENTS)
        }
        locked_names = set(locked_requirements)
        direct_names = set(direct_requirements)
        self.assertEqual(direct_names, DIRECT_PRODUCTION_PACKAGES)
        self.assertTrue(direct_names <= locked_names)
        for name, direct_requirement in direct_requirements.items():
            locked_specifier = next(iter(locked_requirements[name].specifier))
            locked_version = Version(locked_specifier.version)
            self.assertIn(locked_version, direct_requirement.specifier)

    def test_installed_runtime_matches_applicable_lock(self):
        for requirement in load_requirements(RUNTIME_REQUIREMENTS):
            if requirement.marker is not None and not requirement.marker.evaluate():
                continue
            locked_specifier = next(iter(requirement.specifier))
            try:
                installed_version = version(requirement.name)
            except PackageNotFoundError:
                self.fail(f"{requirement.name} is not installed")
            self.assertEqual(installed_version, locked_specifier.version)
