# Deployment profile — implemented design (phase P3)

`PROFILE-001` selected **Option C**: a signed external manifest is the source of
truth for feature availability, and a database table caches the resolved set for
querying without ever being authoritative. This document describes what the code
does. The option comparison that led here is in `DEPLOYMENT_PROFILE_OPTIONS.md`
and is not repeated.

## Three separate controls

| Control | Where it lives | Question it answers |
|---|---|---|
| Feature availability | `common/deployment/`, signed manifest | May this deployment run the module at all? |
| Role permission | `accounts/access.py` | May this role use it? |
| Object scope | each app's `selectors.py` | Which rows may this user see? |

They are checked independently and none substitutes for another. Enabling a
feature grants no capability to any role; disabling one removes no capability
and, critically, **deletes no data** — the gate is on access, never on storage.
`common/tests/test_deployment_profile.py` proves each of these separately.

## Manifest format

An envelope carries a base64 payload and its detached Ed25519 signature. The
signature covers the exact payload bytes, and those same bytes are what gets
parsed, so no re-serialisation can change what was signed.

```json
{
  "manifest_version": 1,
  "algorithm": "ed25519",
  "key_id": "dolphin-2026",
  "payload": "<base64 of the payload JSON below>",
  "signature": "<base64 of the 64-byte Ed25519 signature>"
}
```

```json
{
  "manifest_version": 1,
  "profile_id": "client-1",
  "issued_at": "2026-08-15T00:00:00Z",
  "features": ["customers", "leads", "sales"]
}
```

## Everything that fails closed

`common/deployment/manifest.py` refuses, with no partial-trust outcome and no
default-open branch, a manifest that is:

- missing, unreadable, larger than 64 KiB, or not UTF-8 JSON;
- of an unsupported envelope or payload version;
- signed with an algorithm other than `ed25519`;
- signed by a key id that is not configured as trusted (an empty trusted-key
  mapping therefore verifies nothing);
- tampered with in any byte of payload or signature;
- issued for a `profile_id` this release does not know;
- naming a feature this release does not ship;
- naming a feature whose dependencies are not also enabled;
- repeating a feature, or missing `issued_at`.

A refusal raises `ImproperlyConfigured` from `AppConfig.ready`, so the process
does not start. In addition, `feature_enabled()` returns `False` for any name
absent from the registry, so a typo in a gate denies rather than grants.

## Keys

Generate the signing key once, with OpenSSL, on a machine the platform owner
controls:

```bash
openssl genpkey -algorithm ed25519 -out dolphin-manifest-signing.pem
openssl pkey -in dolphin-manifest-signing.pem -pubout -outform DER | tail -c 32 | base64
```

The private key never reaches a customer host and never enters this repository.
Only the base64 public key is configured, through
`KARIZ_DEPLOYMENT_MANIFEST_KEYS` as `key_id:base64_public_key` pairs. Issue a
manifest with:

```bash
python scripts/sign_deployment_manifest.py \
    --private-key dolphin-manifest-signing.pem \
    --key-id dolphin-2026 \
    --profile-id client-1 \
    --feature customers --feature leads --feature sales \
    --output manifest.json
```

`scripts/` is excluded from the application image by `.dockerignore`, so the
signing tool is not part of what ships.

### Signature implementation

Verification is `common/deployment/ed25519.py`, the RFC 8032 algorithm written
out in the repository rather than pulled from a library. The production
dependency set is hash-pinned and must be resolved in a clean Linux CPython 3.13
image (`docs/ops/DEPENDENCIES.md`), which the current development host cannot
do; an in-repository implementation keeps the phase unblocked with no new
dependency. It is checked against two independent authorities:

- the RFC 8032 section 7.1 test vectors, for both verification and signing;
- OpenSSL 3.5.5, which accepts signatures this code produces and produces
  signatures this code accepts, with byte-identical output for the same key and
  message.

If a future release adds `cryptography` through the reviewed dependency process,
this module can be replaced behind the same `verify()` signature without
changing the manifest format or the authority model.

## The database cache

`common.models.DeploymentProfileCache` is a single row holding the resolved
profile id, feature list, source, and the manifest fingerprint (SHA-256 of the
envelope). It exists so admin screens and reports can query and join; it is
never read to decide access.

This is what makes restore safe. A `pg_restore` of an older dump brings back
whatever row that dump contained, possibly naming features the deployment is no
longer entitled to run. Because no decision consults the row, the stale content
changes nothing, and `common/deployment/cache.py` rewrites it from the manifest
before returning it. Rolling the manifest back likewise takes effect at once,
with the cache following.

## Deployment

`config/production_settings.py` sets `DEPLOYMENT_MANIFEST_REQUIRED = True`, so a
customer deployment refuses to start without a manifest that verifies. The
manifest is bind-mounted read-only into the `web` and `migrate` services at
`/profile/manifest.json` from `KARIZ_DEPLOYMENT_MANIFEST_PATH`.

Development and the automated test suite may run without a manifest. They then
use the built-in profile named `development`, which enables every registered
feature. This is a development convenience only: production cannot reach it,
because the required flag is set there and is covered by a test.

## Registered features and profiles

Feature dependencies are read off the data model, not invented: a feature
depends on another only where a non-nullable foreign key makes its rows
impossible without the other module's rows.

| Feature | Requires |
|---|---|
| `customers` | — |
| `products` | — |
| `inbound_sms` | — |
| `audit_log` | — |
| `leads` | `customers` |
| `sales` | `customers`, `leads` |
| `sales_documents` | `customers` |
| `after_sales` | `customers` |
| `inventory` | `products` |
| `quotations` | `customers`, `products` |
| `orders` | `customers`, `products` |
| `invoices` | `customers`, `products` |
| `payments` | `customers`, `invoices` |
| `customer_ledger` | `customers` |
| `reports` | `customers`, `sales` |
| `internal_it_role` | — |

Profile ids known to this release: `client-1`, `demo`, `development`. A valid
signature for an unregistered id is still refused.

## The `client-1` day-one feature set

The manifest is external and signed by the platform owner, so the authoritative
list lives in that file and not in this repository. What this repository fixes
is which set the first operational deployment is *meant* to carry, so the
manifest can be issued without guesswork and so a mismatch is visible:

```text
customers  products  leads  sales  sales_documents  after_sales
inventory  quotations  orders  invoices  payments  customer_ledger
reports  audit_log
```

Fourteen of the sixteen registered features. Two are deliberately withheld:

* **`inbound_sms`** — the module is built and provider-neutral, but no SMS
  provider contract, credential, or owner has arrived, so a deployment that
  enabled it would show a report with nothing behind it.
* **`internal_it_role`** — this one gates a *role* rather than a module. Client-1
  policy is that only a Platform Admin administers users, so the `company_it`
  role is not assignable there: it is absent from the role selector and
  `change_user_role` refuses it at the API. Another deployment wanting an
  on-site technical account simply lists it in its manifest.

Withholding either removes the route, the API, and the navigation entry while
keeping every stored row, and enabling one later is a manifest change with no
code change and no migration.

`ClientOneDayOneProfileTests` in `common/tests/test_deployment_profile.py`
checks this set against the dependency table and asserts the withheld module is
actually absent rather than merely unlinked.

## Deliberately not included

No expiry, no remote kill-switch, no periodic online activation, and no forced
shutdown. `PROFILE-001` excludes all of these from this phase; adding any of
them needs a separate product-owner decision.

## Honest limit

Signature verification raises the effort of tampering and makes it detectable.
It does not defeat an attacker who owns the hardware and is willing to patch the
verification out of the binary. That matches the threat model in
`DOLPHIN_PROJECT_HANDOFF.md` section 8 and is the reason this work pairs with the
backend packaging question in roadmap phase P12 rather than closing it.
