# SMS provider adapter activation requirements

Current state: `BLOCKED_EXTERNAL`. Kariz stores and reports normalized inbound envelopes internally. It has no live provider adapter and exposes no webhook.

The following exact external material is required before a provider route can be designed or enabled:

- official provider API/webhook documentation, version, production and sandbox base URLs, and change policy;
- exact authentication/signature algorithm, canonical byte sequence, required headers, key identifier rules, secret rotation/revocation flow, and official valid/invalid signature vectors;
- replay contract: provider event timestamp/nonce fields, allowed clock skew, redelivery window, duplicate behavior, and external message-ID uniqueness lifetime;
- complete inbound payload schema, content type/encoding, maximum request size, nullable/optional rules, timestamp timezone/precision, error payloads, and bounded official examples;
- exact sender and recipient/service-line formats, including whether short codes can occur, plus provider-owned normalization rules;
- retry schedule, timeout, ordering, concurrency, acknowledgement status codes, rate limits, maintenance/SLA, and incident contact;
- transport controls such as mTLS or documented source ranges when offered; source IP alone is not accepted as message proof;
- a legal/privacy decision for message-body retention, redaction, access, deletion/hold, audit, backup, and data-processing terms. Current policy is `not_retained` and cannot be widened by an adapter;
- dedicated sandbox credentials and provider-side callback registration supplied through the approved secret channel, never documentation or source control;
- one provider-issued sandbox event and one rejected replay/signature example for automated integration tests;
- production enablement owner, rollback/disable procedure, monitoring fields that contain no body or secret, and final UAT acceptance.

Activation must add a provider-specific adapter behind `InboundSMSProviderAdapter`, verify authentication before parsing business fields, apply request/replay bounds, call the existing normalized storage service, add provider-contract and real sandbox proof, and then explicitly add one route. No generic unsigned ingest route is allowed.
