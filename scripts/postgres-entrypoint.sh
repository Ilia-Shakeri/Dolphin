#!/bin/sh
set -eu

case "${FROOSHBIN_ALLOW_LEGACY_DB_IDENTITIES:-false}" in
  true|false) ;;
  *) echo "FROOSHBIN_ALLOW_LEGACY_DB_IDENTITIES must be true or false." >&2; exit 64 ;;
esac

is_database_name() {
  case "$1" in
    frooshbin|frooshbin_*) return 0 ;;
    kariz|kariz_*|forooshbin|forooshbin_*)
      [ "${FROOSHBIN_ALLOW_LEGACY_DB_IDENTITIES:-false}" = true ]; return ;;
  esac
  return 1
}

is_role_name() {
  case "$1" in
    frooshbin_*) return 0 ;;
    kariz_*|forooshbin_*)
      [ "${FROOSHBIN_ALLOW_LEGACY_DB_IDENTITIES:-false}" = true ]; return ;;
  esac
  return 1
}

is_database_name "${POSTGRES_DB:-}" || {
  echo "POSTGRES_DB must use the frooshbin identity." >&2; exit 64;
}
is_role_name "${POSTGRES_USER:-}" || {
  echo "POSTGRES_USER must use the frooshbin_ identity." >&2; exit 64;
}

[ "${1:-}" != "--frooshbin-preflight-only" ] || exit 0

exec /usr/local/bin/docker-entrypoint.sh "$@"
