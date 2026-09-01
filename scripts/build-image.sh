#!/bin/sh
# Build the application image, tagged from VERSION.
#
#   ./scripts/build-image.sh            build, tagged dolphin-app:v<VERSION>
#   ./scripts/build-image.sh --save     also write dolphin-app-v<VERSION>.tar.gz
#
# Two frictions this removes, both met in practice:
#
#   * `docker build .` on its own fails with "base name (${PYTHON_BASE_IMAGE})
#     should not be blank". The Dockerfile pins its base by digest through a
#     build argument and takes TARGETPLATFORM explicitly, so a bare build was
#     never going to work and the runbook said to run one anyway.
#   * the tag was typed by hand, so it could name a version the image did not
#     contain. It is read from VERSION here, which is the same file the
#     application serves and the footer prints, so the two cannot disagree.
set -eu

fail() {
    echo "error: $1" >&2
    exit 2
}

cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

[ -f Dockerfile ] || fail "no Dockerfile here; run this from the repository."
[ -f VERSION ] || fail "no VERSION file; the image tag is read from it."

version="$(tr -d '[:space:]' < VERSION)"
[ -n "$version" ] || fail "VERSION is empty."
image="dolphin-app:v${version}"

# The base image is pinned by digest and reviewed before use, so it is not
# guessed here. Set it in the environment, or record it in .python-base-image
# next to this repository — that file is git-ignored, because which digest has
# been reviewed is a property of your build machine and its date, not of the
# source.
if [ -z "${PYTHON_BASE_IMAGE:-}" ] && [ -f .python-base-image ]; then
    PYTHON_BASE_IMAGE="$(tr -d '[:space:]' < .python-base-image)"
fi
if [ -z "${PYTHON_BASE_IMAGE:-}" ]; then
    cat >&2 <<'BASE'
error: PYTHON_BASE_IMAGE is not set. The Dockerfile pins its base by digest and
       will not build without one. Take the digest of the reviewed base image:

           docker pull python:3.13-slim
           docker inspect --format='{{index .RepoDigests 0}}' python:3.13-slim

       then record it once, next to this repository:

           echo '<that value>' > .python-base-image

       or export PYTHON_BASE_IMAGE for a single build.

       Use the RepoDigests value, not the image ID from `docker image ls`: an
       image ID identifies the config on this machine only and will not resolve
       anywhere else.
BASE
    exit 2
fi

# The Dockerfile asserts this is amd64 before installing wheels, because the
# requirements are hash-pinned for that platform.
platform="${TARGETPLATFORM:-linux/amd64}"

echo "==> building $image"
echo "    base:     $PYTHON_BASE_IMAGE"
echo "    platform: $platform"
docker build \
    --build-arg PYTHON_BASE_IMAGE="$PYTHON_BASE_IMAGE" \
    --build-arg TARGETPLATFORM="$platform" \
    -t "$image" \
    .

# Read the version back out of what was actually built. Cheap, and it is the
# same check the release performs before deploying — better to learn here.
built="$(docker run --rm --entrypoint cat "$image" /app/VERSION 2>/dev/null | tr -d '[:space:]')"
[ "$built" = "$version" ] || fail "built image contains VERSION=$built, expected $version."
echo "==> $image contains VERSION=$built"

if [ "${1:-}" = "--save" ]; then
    archive="dolphin-app-v${version}.tar.gz"
    echo "==> saving $archive"
    docker save "$image" | gzip > "$archive"
    ls -lh "$archive"
fi

echo
echo "Next: copy the archive to the host, then from the deployment directory:"
echo "    docker load -i <archive>"
echo "    git pull --ff-only && ./scripts/deploy.sh v${version}"
