# Deployment profile — design options (phase P0R.3)

ForooshBin ships one shared codebase to multiple customer deployments. Feature
availability, role permission, and object/data scope are three separate
controls; this document is only about the first one — how a deployment learns
which features it is allowed to run.

**Status: comparison only. No option is approved.** `PROFILE-001` in
`KARIZ_PROJECT_HANDOFF.md` records that architecture discovery is approved and
implementation is not. No `DeploymentProfile` model, migration, or feature-gate
code may be written until the product owner selects one option below.

**Nothing here is implemented today.** The current code has no profile or
feature-flag mechanism of any kind. Client-1 policies such as "`company_it` is
disabled by default" are today operational policy (never create such an
account), not a technical lock.

## Requirements every option must satisfy

Taken from the closed product-owner decisions, not invented here:

1. One shared codebase; no permanent customer fork; no `if client_name == ...`.
2. Feature availability, role permission, and object scope stay separate.
3. Disabling a feature must never delete historical data.
4. An unknown profile or an invalid feature dependency must fail closed.
5. The customer may hold Administrator access on their own host.
6. Update and rollback authority belongs to the product owner, not the customer.

## The three options

```text
Option A — signed external deployment manifest
  A signed file (or signed env-delivered blob) outside the database declares
  the enabled feature set. The app verifies the signature at startup with an
  embedded public key and holds the result in memory.

Option B — database-backed DeploymentProfile
  A Django model/table, populated per deployment, is the source of truth.
  Feature checks query it (with normal caching).

Option C — signed manifest plus runtime database cache
  The signed manifest is the sole source of truth; a database table caches the
  resolved feature set for fast queries and reporting, and is re-derived from
  the manifest at every startup. The cache is never authoritative.
```

## Comparison

| Criterion | Option A — signed manifest | Option B — database profile | Option C — manifest + cache |
|---|---|---|---|
| Modification authority | Product owner only; customer cannot forge without the private key | **Anyone with database access, including a customer DBA/Administrator** | Product owner only; cache edits are overwritten at startup |
| Signature verification | Yes, native to the design | None available — a row has no provenance | Yes, on the manifest |
| Fail-closed behaviour | Missing/invalid signature → refuse to serve | Missing row → must be coded to deny; easy to get wrong and default open | Missing/invalid manifest → refuse to serve, regardless of cache contents |
| Startup failure behaviour | Hard fail with a clear operator error; no partial boot | Depends on migration state; a fresh database can boot with no profile at all | Hard fail on manifest; cache rebuild failure is non-fatal only if the manifest already validated |
| Offline operation | Full; file is local | Full | Full |
| Feature dependencies | Validated once at load; invalid combinations refuse startup | Must be validated on every read or on write; drift possible | Validated once at load, then cached |
| Role / feature / object-scope separation | Clean — manifest carries features only, never roles or object scope | Risk of scope creep: a table invites adding role columns and blurring the three controls | Clean, same as A |
| Auditing | Manifest version/hash logged at startup; changes are release events | Row changes need their own audit trail; a direct SQL update can bypass it | Startup log plus queryable cache for reporting |
| Backup/restore impact | None — manifest is not customer data; restore cannot change entitlements | Profile travels inside the dump; **restoring an old backup can silently re-enable a removed feature** | Cache travels in the dump but is rebuilt from the manifest, so a stale restore self-corrects |
| Rollback | Independent of the database; roll back the manifest with the artifact | Coupled to schema/data state | Independent; cache follows automatically |
| Customer-host Administrator threat | Resists tampering: editing the file invalidates the signature. Cannot stop key extraction from the shipped binary if the attacker is determined | **No resistance** — Administrator edits the row and enables anything | Same resistance as A; cache tampering is ineffective |
| Multi-customer portability | High — one artifact, per-customer manifest | Medium — needs a seeding/migration step per deployment | High |
| Branding separation | Manifest can carry the branding profile id alongside features | Possible, but mixes entitlement and presentation in customer-writable storage | Same as A |
| Secret separation | Only a public key ships; the private signing key never reaches the customer host | No key material, but also no integrity guarantee | Same as A |

## Honest limits

- No option achieves absolute secrecy or absolute tamper-proofing against an
  attacker who owns the hardware and is willing to patch the binary. Signature
  verification raises effort and makes tampering detectable; it does not make
  it impossible. This matches the threat model in `KARIZ_PROJECT_HANDOFF.md` §8.
- Signing only helps if the verification path itself is not trivially patched
  out. That argues for combining this work with the backend packaging decision
  in P12 rather than treating it as fully solved on its own.
- Option B's backup/restore behaviour is the most under-appreciated risk: it
  turns an ordinary disaster-recovery action into a silent entitlement change.

## Engineering assessment (recommendation — requires approval)

**Option C** is the recommended shape, with **Option A** as the acceptable
smaller-scope fallback.

Option C keeps the authority and integrity properties of a signed manifest
while giving the application a normal queryable table for admin screens,
reports, and joins — without ever letting that table become the source of
truth. It is strictly better than Option B on every security-relevant row, and
better than Option A only on convenience.

Option B should not be selected: it places entitlement control inside storage
the customer can edit, and it makes a restore-from-backup capable of changing
what the deployment is licensed to run.

If the product owner prefers the smallest possible first step, Option A alone
is defensible and can be upgraded to Option C later without changing the
manifest format or the authority model.

## What selecting an option unblocks

Roadmap phase P3 (deployment-profile implementation) stays blocked until one
option is chosen. P1.7 (removing Sales Manager user administration) also
depends on this indirectly: the technical choice there is whether to delete the
`users.manage_agents` capability outright or gate it behind the selected
profile mechanism so other deployments can retain it.
