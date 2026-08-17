# TLS edge procedure

Status: repository TLS configuration is fail closed; certificate, hostname, Nginx runtime, and public scanner proof remain external.

The production Compose stack terminates TLS at its own Nginx service. Port 80 serves only the local liveness route and a permanent redirect to the one approved host. Application, admin, API, and static traffic use port 443. Nginx sends a fixed `X-Forwarded-Proto: https` value to the unexposed application service.

## Required inputs

Before starting the stack, the deployment owner must approve:

- one lowercase public hostname (or, with no domain, one static public IP — the certificate must then carry `subjectAltName=IP:`);
- a certificate chain valid for that hostname;
- its matching private key;
- protected host paths for the chain and key;
- the renewal owner and renewal test date.

Set `KARIZ_PUBLIC_HOST` to the exact host. `DJANGO_ALLOWED_HOSTS` must contain only that one value. `DJANGO_CSRF_TRUSTED_ORIGINS` must contain only `https://` plus that exact host, with no wildcard, dot prefix, sibling, port, slash, or extra entry. Set `KARIZ_TLS_CERT_PATH` and `KARIZ_TLS_KEY_PATH` to the approved host files. Compose mounts both read-only at fixed Nginx paths. Never place certificate or key content in the repository, image, command line, log, or evidence record.

Production validation rejects SSL redirect off, HSTS below one year, unsafe host values, host/origin mismatch, and any edge HSTS text that differs from the Django settings. The single exception is an explicit `DJANGO_SECURE_HSTS_SECONDS=0` with an empty `KARIZ_HSTS_HEADER`, which turns HSTS off entirely — intended for a staging or IP-only deployment on a self-signed certificate, where a one-year pin would leave the operator unable to click past their own warning; see `CLIENT1_LINUX_STAGING_GUIDE.md` §2 scenario B. Off must be off at both layers: subdomain and preload HSTS are refused alongside it, and Nginx emits no header for an empty value. Nginx owns that checked header on every HTTPS status, including static and edge-generated errors; it hides the upstream copy to prevent duplicate policy headers. Subdomain HSTS and preload stay off unless the owner proves every affected subdomain is HTTPS and approves the wider scope.

## Preflight

Confirm the approved chain and key files exist and are readable only through the deployment secret process. Do not display file content. Then run:

```powershell
docker compose config --quiet
python scripts/validate_release_images.py
docker compose pull nginx
```

The quiet config check must fail when either TLS path is absent. Source tests do not prove that the certificate and key match.

After start, inspect Nginx health and restricted logs locally. Stop if Nginx cannot load the chain/key, if port 80 serves application content, if the redirect host differs, or if the certificate name/chain is wrong.

## Live proof

From an approved external client, prove:

- HTTP redirects to the fixed approved HTTPS host;
- TLS 1.0 and 1.1 fail while TLS 1.2 and 1.3 work;
- certificate name, chain, validity, and renewal path are correct;
- login, CSRF, secure cookies, HSTS, static files, API errors, and request IDs work through HTTPS;
- direct application port 8000 and database port 5432 are not public;
- a reviewed TLS scanner has no release-blocking result.

Record only host, time, release reference, tool version, status, and reviewer. Do not store cookies, headers with credentials, key data, or raw restricted logs.

## Renewal

Renew into protected host files using the approved certificate process. Validate the new pair before cutover, keep the prior valid pair recoverable, then reload or restart only Nginx through the approved change. Repeat hostname, chain, expiry, redirect, health, login, and scanner proof. If any check fails, restore the prior pair and reload Nginx; do not weaken TLS or expose HTTP application traffic.
