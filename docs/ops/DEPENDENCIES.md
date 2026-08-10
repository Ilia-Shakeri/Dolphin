# Dependency lock

> This document records the dependency contract and dated evidence, not live project status. Current progress, blockers, evidence, and exact next action exist only in `KARIZ_PROJECT_HANDOFF.md`.

## Files

- `requirements-direct.txt` holds human-set compatibility ranges for direct production packages.
- `requirements.txt` is the exact version-and-SHA-256 runtime lock installed by the container.
- Runtime-only transitive packages are pinned and every allowed wheel is hashed, so package selection and package bytes fail closed.

## Current target and evidence

- Container target: CPython 3.13 on `linux/amd64`. The Dockerfile rejects another target platform, accepts no mutable base default, and requires `PYTHON_BASE_IMAGE` as one reviewed `repository@sha256:...` input.
- Lock audit date: 2026-08-10.
- Installed metadata used for the lock reports Django 5.2.17 supports Python 3.10 or newer and lists Python 3.13 as supported.
- Each locked package reports Python 3.13 compatibility in installed package metadata.
- `psycopg[binary]` and its binary distribution use the same exact version.
- `tzdata` is locked behind a Windows marker; the Linux container does not install it.
- The lock contains reviewed CPython 3.13 Linux-amd64 hashes. The three platform wheels also contain Windows-amd64 hashes so the guarded local setup remains usable.
- `pip download --require-hashes --only-binary=:all:` passed for both `manylinux_2_17_x86_64/cp313` and `win_amd64/cp313` on 2026-08-10. This proves lock resolution and hashes, not a container build.

## Safe update flow

1. Change direct ranges only when an upgrade is approved.
2. Resolve the full tree in a clean Linux-amd64 container using the same Python 3.13 base.
3. Replace every version and every Linux-amd64 artifact hash in `requirements.txt`; do not merge a partial resolver result. Refresh the Windows-amd64 hashes for compiled wheels in the same review.
4. Prove both target sets with `pip download --require-hashes --only-binary=:all:` and run `python -m pip check` plus the dependency contract test.
5. Run the full backend test suite, schema checks, and a clean container build.
6. Review package release and security notes before deployment.

Validate all four release image inputs before a build or deploy. The check prints no reference value:

```powershell
python scripts/validate_release_images.py
docker build --platform linux/amd64 --build-arg PYTHON_BASE_IMAGE=$env:PYTHON_BASE_IMAGE --tag kariz-review-build .
```

Push the reviewed application build, resolve its registry digest, and set that exact digest as `KARIZ_APP_IMAGE`. Both `migrate` and `web` use that one image. Production Compose never builds local source.

## Open reproducibility gaps

- No digest value is guessed or committed. Release input validation requires exact application, Python-base, PostgreSQL, and Nginx digest references supplied by the approved artifact process.
- A clean Linux-amd64 container build still needs a host with the container tool installed.
- Registry digest review, artifact scan, and software-bill evidence still belong to the exact release artifact gate.
