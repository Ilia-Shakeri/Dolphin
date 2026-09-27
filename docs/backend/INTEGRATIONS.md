# Integrations framework

Since 2.21.0 every connection to an outside system goes through one framework
(`integrations/`): providers, encrypted settings, a domain-event outbox,
inbound and outbound webhooks, API tokens, contact matching and one admin page
(«یکپارچه‌سازی‌ها», `/settings/integrations/`). The product decisions behind it
are D9–D17 in [`docs/PERSON_PROFILE_AND_INTEGRATIONS_PLAN.md`](../PERSON_PROFILE_AND_INTEGRATIONS_PLAN.md).

## Features and who may use them

| Feature | Gives | Depends on |
|---|---|---|
| `integrations` | connections, the outbox, inbound webhooks, the page | — |
| `outbound_webhooks` | pushing events to subscribers | `integrations` |
| `public_api` | `Authorization: Bearer dol_…` tokens | `integrations` |

All three are off by default. Everything on the page and behind its API is the
Platform Admin's (the same rule as the SMS gateway settings): each connection
holds credentials that act for the whole deployment. SMS and post keep their
own settings pages and appear on this page as built-in rows
(`common/integrations.py`).

## Secrets

`integrations/crypto.py` stores an integration's secret fields as one Fernet
token (AES-128-CBC + HMAC-SHA256, the reviewed `cryptography` package) under
`DOLPHIN_SECRETS_KEY`, which lives only in `secrets/.env`. Secrets are
write-only: the API accepts them, never returns them, and shows a masked hint;
a blank secret on edit keeps the stored value. Nothing secret is written to the
audit log or to `IntegrationLog` (`services.redact`). Without a key the panel
runs but refuses to store a secret. Rotation: put the new key first and the old
one after a comma, re-save each connection, then drop the old key.

## Adding a provider

1. Subclass `integrations.providers.Provider` in `integrations/providers/<name>.py`:
   `key` (stable — it is stored on every `Integration` row), `name`,
   `description`, `capabilities` (`telephony`, `messaging`, `sms`, `email`,
   `payment`, `accounting`, `webhook`), `fields` (a tuple of `ConfigField` —
   the admin form is built from it; `secret=True` or `kind="password"` fields
   are encrypted; `ltr=True` for a host, path or pattern typed left to right),
   and optionally `required_feature`, `singleton`, `accepts_webhooks`. The
   Asterisk provider (`telephony/provider.py`, [TELEPHONY.md](TELEPHONY.md))
   is the fullest example: a listener service, a periodic job and a test.
2. Implement what applies: `validate(config, secrets)` for cross-field rules,
   `test_connection(integration, config, secrets)` returning a
   `ConnectionResult`, `verify_inbound(...)` / `handle_inbound(...)` for
   webhooks, and `integrations.worker.register_service(...)` /
   `register_job(...)` for long-running listeners or periodic syncs.
3. Call `register(YourProvider())` at import, and import the module from
   `IntegrationsConfig.ready()` (or the owning app's `ready()`).
4. Record health with `integrations.services.record_health(integration, ok,
   message)` and traffic with `integrations.services.log(...)`.
5. Tests: a fake of the outside system, never the real one.

## Domain events and the outbox

`integrations.events.emit(event_type, payload, person_type=…, person_id=…,
dedupe_key=…)` writes a `DomainEvent` in the caller's transaction and handles it
right after commit. Handling runs the handlers registered with
`@events.handles(...)` and queues one outbound delivery per matching
subscriber. A failure leaves the event `pending` with its error and a later
`available_at` (1 min, 5 min, 30 min, 2 h, 12 h), then `failed` after six
attempts. `dedupe_key` makes the same fact emit once. Event types:
`call.started`, `call.answered`, `call.ended`, `call.missed`,
`message.received`, `message.sent`, `payment.received`.

`payment.received`, and `message.received`/`message.sent` for SMS, are emitted
from `post_save` receivers in `integrations/signals.py`, so billing and
communications do not import this app.

## Inbound webhooks

`POST /api/v1/integrations/<id>/webhook/` — no session; the provider's
signature is the authentication. The generic provider expects
`X-Dolphin-Signature: sha256=<hex HMAC-SHA256 of the raw body>` under its
signing secret and a body such as:

```json
{"id": "tg-1", "type": "message.received", "channel": "telegram",
 "from": "+989121234567", "text": "…"}
```

A request is idempotent on `Idempotency-Key`, else `id`, else the body hash;
a repeat answers 200 and does nothing. A disabled or unknown connection is a
404; a bad signature is a 403 and a log row.

## Outbound webhooks

Each delivery is `POST {"id", "type", "occurred_at", "data"}` with
`X-Dolphin-Event`, `X-Dolphin-Delivery` and
`X-Dolphin-Signature: t=<unix>,v1=<hex HMAC-SHA256 of "<t>.<body>">`. A
receiver should recompute the signature with the subscriber's secret (shown
once, when the subscriber is created) and reject a timestamp more than five
minutes old. Targets must be `https://` on a public address — private,
loopback and link-local addresses are refused, which keeps Dolphin from being
pointed at its own database or a metadata service.

## API tokens

A token is bound to one CRM user (never the Platform Admin) and carries exactly
that user's roles, capabilities, overrides and object scope; its scopes narrow
it further (`read` = safe methods only). Only the SHA-256 is stored; the plain
token is shown once. A revoked, expired or unknown token, or one whose user is
inactive, is refused. With `public_api` off the header is ignored.

## Contact matching

`integrations.matching.match_phone(raw)` → `[Match(person_type, person_id,
name, how)]`: exact E.164 on active customer phones, then colleagues
(`User.normalized_phone`), then the last ten digits (PBX trunk prefixes), then
numbers already called (`Interaction.normalized_phone`). It ignores who is
asking; what a reader may see of the match is decided where it is shown.

## The worker

`manage.py run_integrations_worker` (Compose service `integrations-worker`,
profile `integrations`) sweeps the outbox and due deliveries every few seconds
and runs provider services and jobs. It never exits on an error and stops
cleanly on SIGTERM. `process_domain_events` does one sweep;
`prune_integration_logs --days 90` trims the log.
