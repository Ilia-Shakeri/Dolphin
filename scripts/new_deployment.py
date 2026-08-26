#!/usr/bin/env python3
"""Provision a new ForooshBin deployment: its .env, its identifiers, its secrets.

Every deployment this product ships is the same code with a different `.env`, a
different set of volumes, and a signed manifest naming the features it may run.
Assembling those by hand is where deployment mistakes come from — a role name
that does not match the volume it was provisioned against, a project name that
collides with a live stack, a password typed into two places and mistyped in
one. This writes all of it from one answer set.

What it does NOT do is anything irreversible or anything requiring judgement it
does not have. It creates no volumes, starts no containers, touches no running
deployment, and never overwrites an existing `.env`. It writes one file and
prints the commands you would run next.

The feature list and the dependency rules come from
`common/deployment/registry.py` — imported, never copied — so this tool and the
running application can never disagree about what a feature is or what it needs.

Usage:

    scripts/new_deployment.py --slug tiara --host crm.tiara.ir --out /srv/forooshbin/tiara

Add `--features customers,products,invoices` to choose explicitly; omit it and
the deployment gets this release's default set. `--list-features` prints what is
available and exits.

Secrets are generated here and written only into the `.env` at mode 0600. They
are never printed, never logged, and never passed on a command line.
"""

import argparse
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from common.deployment.registry import (  # noqa: E402
    DEFAULT_FEATURES,
    FEATURE_DEPENDENCIES,
    FEATURES,
    PROFILES,
    missing_dependencies,
    unknown_features,
)


#: PostgreSQL identifier rules, which every derived name has to satisfy:
#: lowercase, starts with a letter or underscore, and never the reserved `pg_`
#: prefix. Kept short enough that `<slug>_migration` stays inside 63 characters.
SLUG_PATTERN = re.compile(r"\A[a-z][a-z0-9_]{1,40}\Z")
#: A hostname, not a URL. Checked because it lands in DJANGO_ALLOWED_HOSTS and
#: in the nginx server_name, where a scheme or a path silently breaks both.
HOST_PATTERN = re.compile(r"\A[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\Z")


class ProvisioningError(Exception):
    """Something the operator must fix before a deployment can be written."""


def password():
    """A generated secret.

    `token_urlsafe(48)` is 64 characters of URL-safe base64 over 384 bits.

    The length is not arbitrary: `config/production_env.py` refuses to start a
    deployment whose `DJANGO_SECRET_KEY` is under 50 characters, and the 43 this
    used to generate sat just below that line — every provisioned deployment
    would have failed on first boot. One length is used for all five secrets so
    there is no second value to get wrong.

    The alphabet matters as much as the length: these values are written into a
    `.env` read by shell tooling and by Compose, so a quote or a `$` would
    eventually be interpolated by something.
    """
    return secrets.token_urlsafe(48)


def resolve_features(requested):
    """The feature set to sign, with dependencies pulled in and explained.

    A feature whose dependency is missing is not an error to report and stop on
    — it is a choice the operator did not know they were making. `invoices`
    without `customers` describes a deployment that cannot function, so the
    dependency is added and the addition is stated. Refusing instead would just
    mean the operator adds it by hand without learning why.
    """
    enabled = set(requested)
    unknown = unknown_features(enabled)
    if unknown:
        raise ProvisioningError(
            f"This release does not ship: {', '.join(sorted(unknown))}. "
            "Run --list-features to see what it does."
        )
    added = {}
    # Fixed point: a dependency can itself have dependencies.
    while True:
        missing = missing_dependencies(enabled)
        if not missing:
            break
        for feature, required in missing.items():
            added.setdefault(feature, set()).update(required)
            enabled |= set(required)
    return frozenset(enabled), added


def env_lines(*, slug, host, image, profile, manifest_path, manifest_keys, retention_days):
    """The `.env` for this deployment, as ordered lines.

    Names are derived from the slug rather than asked for separately, because
    every one of them has to agree with the others: the database role in the
    `.env`, the role the bootstrap script provisions, and the role the backup
    job authenticates as are the same string in three places, and a deployment
    where they disagree fails in ways that took a day to diagnose once already.
    """
    return [
        "# Written by scripts/new_deployment.py. Secrets in this file were",
        "# generated at provisioning time and exist nowhere else - there is no",
        "# copy to recover them from. Back this file up somewhere private, and",
        "# never commit it.",
        f"# Provisioned {datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')}",
        "",
        "# --- identity ---------------------------------------------------------",
        "# Stable for the life of the deployment. The version belongs to the",
        "# image tag and must never be put here: a project name per version means",
        "# two stacks sharing one database volume, which corrupts it.",
        f"KARIZ_COMPOSE_PROJECT_NAME={slug}",
        f"KARIZ_APP_IMAGE={image}",
        "KARIZ_POSTGRES_IMAGE=postgres:17-alpine",
        "KARIZ_NGINX_IMAGE=nginx:alpine",
        "# PYTHON_BASE_IMAGE is deliberately absent. It is a Dockerfile build",
        "# argument, not a runtime setting, and a customer host never builds.",
        "",
        "# --- Django -----------------------------------------------------------",
        f"DJANGO_SECRET_KEY={password()}",
        "DJANGO_DEBUG=false",
        f"DJANGO_ALLOWED_HOSTS={host}",
        f"DJANGO_CSRF_TRUSTED_ORIGINS=https://{host}",
        f"KARIZ_PUBLIC_HOST={host}",
        "AUDIT_TRUSTED_PROXY_CIDRS=172.16.0.0/12",
        "DJANGO_SECURE_SSL_REDIRECT=true",
        "DJANGO_SECURE_HSTS_SECONDS=31536000",
        "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=false",
        "DJANGO_SECURE_HSTS_PRELOAD=false",
        "KARIZ_HSTS_HEADER=max-age=31536000",
        "",
        "# TLS. These two paths are the only values here you must still fill in:",
        "# a certificate is obtained per deployment and cannot be generated here.",
        "KARIZ_TLS_CERT_PATH=REPLACE-WITH-THE-CERTIFICATE-CHAIN-PATH",
        "KARIZ_TLS_KEY_PATH=REPLACE-WITH-THE-PRIVATE-KEY-PATH",
        "",
        "# --- PostgreSQL -------------------------------------------------------",
        "# Four roles with four distinct passwords, by design: the application",
        "# never holds the credential that can migrate, and the backup job never",
        "# holds one that can write.",
        f"POSTGRES_DB={slug}",
        f"POSTGRES_INIT_USER={slug}_init",
        f"POSTGRES_INIT_PASSWORD={password()}",
        f"POSTGRES_MIGRATION_USER={slug}_migration",
        f"POSTGRES_MIGRATION_PASSWORD={password()}",
        f"POSTGRES_APP_USER={slug}_app",
        f"POSTGRES_APP_PASSWORD={password()}",
        f"POSTGRES_BACKUP_USER={slug}_backup",
        f"POSTGRES_BACKUP_PASSWORD={password()}",
        "POSTGRES_HOST=db",
        "POSTGRES_PORT=5432",
        "POSTGRES_CONNECT_TIMEOUT=3",
        f"POSTGRES_DATA_VOLUME={slug}_postgres_data",
        f"POSTGRES_BACKUP_VOLUME={slug}_postgres_backups",
        f"POSTGRES_BACKUP_RETENTION_DAYS={retention_days}",
        "POSTGRES_RESTORE_TMPFS_SIZE_BYTES=1073741824",
        "",
        "# --- signed deployment manifest ---------------------------------------",
        f"# Profile: {profile} — {PROFILES[profile]}",
        f"KARIZ_DEPLOYMENT_MANIFEST_PATH={manifest_path}",
        f"KARIZ_DEPLOYMENT_MANIFEST_KEYS={manifest_keys}",
        "",
        "# --- optional ---------------------------------------------------------",
        "KARIZ_PDF_RENDERER=",
        "KARIZ_PDF_CHROMIUM_BINARY=",
        "KARIZ_PDF_RENDER_TIMEOUT_SECONDS=20",
        "POSTGRES_SSLMODE=",
        "POSTGRES_SSLROOTCERT=",
        "",
    ]


def write_env(path, lines):
    """Write the `.env`, refusing to replace one that already exists.

    Overwriting would discard secrets that exist in no other copy — the roles in
    the database would keep the old passwords while the file claimed the new
    ones, which is precisely the failure this tool exists to prevent.
    """
    if path.exists():
        raise ProvisioningError(
            f"{path} already exists. Provisioning would replace secrets that "
            "exist nowhere else. Move it aside first if you truly mean to."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_EXCL makes the "already exists" check and the create atomic, and the
    # mode is applied at creation — so the secrets are never briefly
    # world-readable in the window a later chmod would leave open.
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def report(*, slug, host, out_dir, env_path, features, added, profile):
    print(f"Wrote {env_path} (mode 0600).")
    print()
    print("  project        ", slug)
    print("  host           ", host)
    print("  database       ", slug)
    print("  roles          ", ", ".join(f"{slug}_{r}" for r in ("init", "migration", "app", "backup")))
    print("  data volume    ", f"{slug}_postgres_data")
    print("  backup volume  ", f"{slug}_postgres_backups")
    print("  profile        ", profile)
    print()
    print(f"  features ({len(features)}):")
    for feature in sorted(features):
        needs = FEATURE_DEPENDENCIES[feature]
        suffix = f"   (needs {', '.join(sorted(needs))})" if needs else ""
        print(f"    - {feature}{suffix}")
    if added:
        print()
        print("  dependencies added for you:")
        for feature, required in sorted(added.items()):
            print(f"    - {feature} pulled in {', '.join(sorted(required))}")
    print()
    print("Secrets were generated into the .env and are NOT shown here. They")
    print("exist in no other copy - back that file up somewhere private.")
    print()
    print("Next, in order:")
    print()
    print("  1. Put the TLS certificate and key on the host, then set")
    print("     KARIZ_TLS_CERT_PATH and KARIZ_TLS_KEY_PATH in the .env.")
    print()
    print("  2. Sign the deployment manifest, on the machine holding the private")
    print("     key - never on the customer host:")
    print()
    print("     python scripts/sign_deployment_manifest.py \\")
    print(f"       --private-key <key> --key-id <id> --profile-id {profile} \\")
    for feature in sorted(features):
        print(f"       --feature {feature} \\")
    print("       --output <manifest.json>")
    print()
    print("     Copy the manifest to KARIZ_DEPLOYMENT_MANIFEST_PATH and put its")
    print("     public key in KARIZ_DEPLOYMENT_MANIFEST_KEYS.")
    print()
    print("  3. Create the two external volumes:")
    print()
    print(f"     docker volume create {slug}_postgres_data")
    print(f"     docker volume create {slug}_postgres_backups")
    print()
    print("  4. Copy the runtime files into the deployment directory, then bring")
    print("     the database up once so it initialises:")
    print()
    print(f"     cd {out_dir} && docker compose up -d db")
    print()
    print("  5. Release, and create the first administrator:")
    print()
    print("     ./scripts/deploy.sh <image-tag>")
    print("     docker compose run --rm web python manage.py bootstrap_platform_admin --username admin")
    print()
    print("Full detail: docs/ops/FOROOSHBIN_DEPLOYMENT_RUNBOOK.md")


def parse_arguments(argv):
    parser = argparse.ArgumentParser(
        description="Provision a new ForooshBin deployment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list-features", action="store_true",
                        help="print the features this release ships, and exit")
    parser.add_argument("--slug", help="lowercase identifier; names the project, database, roles and volumes")
    parser.add_argument("--host", help="public hostname, e.g. crm.example.ir")
    parser.add_argument("--out", help="deployment directory to write the .env into")
    parser.add_argument("--features", default=None,
                        help="comma-separated; omit for this release's default set")
    parser.add_argument("--profile", default="client-1", choices=sorted(PROFILES))
    parser.add_argument("--image", default="forooshbin-app:latest",
                        help="application image reference for the first release")
    parser.add_argument("--manifest-path", default="/srv/forooshbin/secrets/manifest.json")
    parser.add_argument("--manifest-keys", default="REPLACE-WITH-key-id:base64-ed25519-public-key")
    parser.add_argument("--retention-days", type=int, default=0,
                        help="backup retention; 0 keeps everything")
    return parser.parse_args(argv)


def main(argv=None):
    arguments = parse_arguments(argv)

    if arguments.list_features:
        print(f"{len(FEATURES)} features in this release "
              f"({len(DEFAULT_FEATURES)} on by default):\n")
        for feature in sorted(FEATURES):
            default = "on " if feature in DEFAULT_FEATURES else "off"
            needs = FEATURE_DEPENDENCIES[feature]
            suffix = f"  needs {', '.join(sorted(needs))}" if needs else ""
            print(f"  [{default}] {feature}{suffix}")
        print("\nProfiles:")
        for name, description in sorted(PROFILES.items()):
            print(f"  {name}: {description}")
        return 0

    for name in ("slug", "host", "out"):
        if not getattr(arguments, name):
            sys.stderr.write(f"--{name} is required (or use --list-features).\n")
            return 2

    try:
        if not SLUG_PATTERN.match(arguments.slug) or arguments.slug.startswith("pg_"):
            raise ProvisioningError(
                "--slug must be 2-41 characters, lowercase, starting with a letter, "
                "and must not start with 'pg_' - it becomes a PostgreSQL database "
                "and role name."
            )
        if not HOST_PATTERN.match(arguments.host):
            raise ProvisioningError(
                "--host must be a bare hostname: no scheme, no port, no path."
            )

        requested = (
            {name.strip() for name in arguments.features.split(",") if name.strip()}
            if arguments.features is not None
            else set(DEFAULT_FEATURES)
        )
        if not requested:
            raise ProvisioningError("--features was given but selected nothing.")
        features, added = resolve_features(requested)

        out_dir = Path(arguments.out)
        env_path = out_dir / ".env"
        write_env(env_path, env_lines(
            slug=arguments.slug,
            host=arguments.host,
            image=arguments.image,
            profile=arguments.profile,
            manifest_path=arguments.manifest_path,
            manifest_keys=arguments.manifest_keys,
            retention_days=arguments.retention_days,
        ))
    except ProvisioningError as error:
        sys.stderr.write(f"error: {error}\n")
        return 2

    report(
        slug=arguments.slug,
        host=arguments.host,
        out_dir=out_dir,
        env_path=env_path,
        features=features,
        added=added,
        profile=arguments.profile,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
