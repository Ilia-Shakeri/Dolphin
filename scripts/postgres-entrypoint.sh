#!/bin/sh
set -eu

# The database name and role are the deployment's own choice, so this wrapper
# no longer gates on what they are called. It previously refused to start unless
# they carried a brand prefix, which protected nothing and blocked a staging
# deployment whose roles already existed under their own names.
#
# The identifier shape, the reserved `pg_` prefix, role distinctness and
# password strength are all still enforced — in config/production_env.py, before
# Django will start at all.
#
# The wrapper stays so the preflight flag keeps working and so there is a place
# to put a real check if one is ever needed.

[ "${1:-}" != "--dolphin-preflight-only" ] || exit 0

exec /usr/local/bin/docker-entrypoint.sh "$@"
