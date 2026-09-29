# Telephony — the Asterisk / FreePBX connector and webhook PBXs

Since 2.22.0 Dolphin can connect to an Asterisk PBX (plain Asterisk or
FreePBX) as a provider of the [integrations framework](INTEGRATIONS.md). Calls
are read live over the Asterisk Manager Interface (AMI), matched to a customer
or a colleague, stored as `telephony.Call` rows, corrected from the PBX's own
call records (CDR), and their recordings are played through Dolphin. Since
2.23.0 a call also rings a popup, can be placed from Dolphin (click-to-call),
and reaches the person's timeline, tasks, score and the user's performance
figures. Going live on a customer's PBX, step by step, is
[`docs/ops/ASTERISK_GO_LIVE.md`](../ops/ASTERISK_GO_LIVE.md). The product
decisions behind it are D10–D14 and D20 in
[`docs/PERSON_PROFILE_AND_INTEGRATIONS_PLAN.md`](../PERSON_PROFILE_AND_INTEGRATIONS_PLAN.md).

## Feature and permissions

| Control | What it is |
|---|---|
| Feature `telephony` | the whole module; depends on `integrations` and `customers`; off by default |
| `calls.own` | the calls the user handled (their extension rang or placed it) |
| `calls.company` | every call |
| `calls.recordings` | hearing a recording — of a call already in the user's scope |
| `calls.originate` | placing a call from Dolphin (click-to-call, 2.23.0) |

Defaults (decision D20): sales and after-sales agents `calls.own` +
`calls.originate`; Sales Manager and Company IT `calls.company` +
`calls.originate` + `calls.recordings`; Platform Admin all. Each is adjustable
per user in the permissions matrix (rows «تماس‌های تلفنی» and «ضبط مکالمه»).
The connection itself and the extension map are the Platform Admin's, on
«یکپارچه‌سازی‌ها».

## Data

- `Extension` — one PBX extension (`number`, digits, `*` and `#` only) on one
  connection, optionally mapped to a Dolphin user. A number is unique per
  connection; a user has at most one active extension per connection.
- `Call` — one call, keyed by Asterisk's `Linkedid` (unique per connection).
  `direction` (`inbound`, `outbound`, `internal`), `status` (`ringing`,
  `answered`, `completed`, `missed`, `no_answer`, `busy`, `failed`), the raw
  caller and callee, the outside number in E.164 (`external_number`), the
  extension and user that handled it, the matched person (`person_type` +
  `person_id`), times, `duration` and `billsec` (talk time), hangup cause,
  recording file name, which sources saw it (`seen_by_ami`, `seen_in_cdr`) and
  the last few raw events. A connection that has calls cannot be deleted
  (`PROTECT`); disable it instead. Calls are never deleted.
- `CallNotification` — the per-user popup queue.
- `CdrSyncState` — the CDR cursor and last error per connection.
- `OriginateRequest` (2.23.0) — a call someone asked Dolphin to place: who,
  from which extension, what the PBX dials, the matched person, the `Call` it
  became, and `pending` → `sending` → `sent` or `failed` with the reason.

## The live listener

`telephony/ami.py` is a small asyncio AMI client (no dependency): it logs in,
reads events, sends `Ping` every 20 s, and on any failure reconnects after a
growing, jittered delay (1 s … 60 s). A malformed line or an unknown event is
skipped; the AMI password is sent only in `Login` and never logged.

`telephony/tracker.py` turns events into `Call` rows, per `Linkedid`:

- `Newchannel` opens the call. Direction: an internal caller (a mapped
  extension, or a number no longer than `internal_extension_max_length`)
  dialling an outside number is `outbound`; an outside caller is `inbound`;
  internal to internal is `internal`. The outbound prefix is stripped before
  matching.
- `DialBegin` / `AgentCalled` note who was rung (inbound calls, queues); the
  first mapped extension to ring owns the call until one answers.
- `DialEnd` with `ANSWER`, or `BridgeEnter`, marks it answered by that
  extension.
- The `Hangup` of the last channel ends it: `completed` if answered, else
  `missed` (inbound), else `busy` / `failed` / `no_answer` from the dial status.

Each step emits a domain event — `call.started`, `call.answered`,
`call.ended`, `call.missed` — deduplicated per call, so handlers and outbound
webhooks see each fact once.

The listener runs inside `integrations-worker` (one AMI session per enabled
Asterisk connection; a supervisor re-reads the connections every 30 s, so
enabling, disabling or editing one takes effect without a restart). Its health
— connected, login refused, unreachable — is written to the connection row and
shown on the page. `manage.py run_telephony_listener --integration <id>` runs
one listener in the foreground for debugging; never run it beside the worker
against the same PBX.

## CDR sync

The listener cannot see calls while Dolphin or the network is down; the PBX's
CDR table always has them. Every 5 minutes the worker reads CDR rows newer than
the last run minus a 10-minute overlap from FreePBX's `asteriskcdrdb.cdr`
(MariaDB/MySQL, read with the hash-pinned PyMySQL) and, per `linkedid`,
creates a call the listener missed, corrects `duration` and `billsec` from the
PBX's count, finishes a call left open, and records the recording file name.
It is idempotent. `manage.py sync_cdr [--integration <id>] [--since …]
[--until …]` re-runs a range without moving the cursor. `pbx_timezone` (default
`Asia/Tehran`) interprets the CDR's local `calldate`. The table name is
validated (`[A-Za-z0-9_]`), never interpolated from user text.

## Recordings

Dolphin keeps only the file name; the PBX keeps the audio.
`GET /api/v1/calls/<id>/recording/` checks `calls.recordings` and that the call
is in the reader's scope, then streams the file with HTTP `Range` support
(`200`, `206`, `416`), `Cache-Control: private, no-store`, and one audit row
(`call.recording_played`) per listening, not per seek. Two sources, per
connection:

- `mount` — the PBX's recording directory mounted **read-only** into the `web`
  container at `recordings_path` (FreePBX layout `YYYY/MM/DD/<file>`). Only
  audio suffixes (`.wav`, `.mp3`, `.ogg`, `.gsm`, `.wav49`) are served; a path
  that leaves the root (`..`, absolute, a symlink out) is refused. The
  directory is never served on its own.
- `url` — the PBX serves recordings over `https://` to Dolphin only
  (`recordings_base_url`, optional basic auth); Dolphin fetches the file and
  passes it through. Only that host is ever contacted.

## Click-to-call (2.23.0)

`POST /api/v1/telephony/originate/ {number, person_type?, person_id?}` asks the
PBX to ring the caller's own phone and, when they pick up, dial `number`:

1. The web checks, in order, and refuses in Persian: `calls.originate`
   (403); an active extension of the caller's own on an enabled Asterisk
   connection (400); that connection's health is «متصل» (409); `number` is a
   number (400); the person, if given, is in the caller's scope (400); no
   earlier request of theirs is still being placed (409). It writes an
   `OriginateRequest` and one audit row (`call.originate_requested`) and
   answers 202 at once. Its own throttle: 12 a minute per user.
2. The worker, which holds the live AMI session, claims the connection's
   queued requests every second (a conditional update, so two workers never
   send one call twice), creates the outbound `Call` with
   `Linkedid = dolphin-<uuid>` and sends `Originate` with that id as
   `ChannelId`, `Channel` from the pattern (`Local/{extension}@from-internal`),
   `Context`, `Exten` = what to dial, `CallerID`, `Timeout` and `Async`.
3. The PBX's events then land on that row like any other call. Only the
   *outside* party answering answers it — the user's own phone picking up
   first does not — and an `OriginateResponse: Failure` (their phone was
   busy, did not answer, or is unreachable) closes it as `busy`, `no_answer`
   or `failed`.
4. A request nobody claimed within 30 seconds fails with «مرکز تلفن درخواست را
   در زمان مقرر نپذیرفت». The page polls `GET telephony/originate/<id>/` once a
   second and says what happened.

What is dialled: an internal extension as typed; an Iranian number in any
stored shape (`+98912…`, `0098…`, `912…`) the way a phone in Iran dials it
(`0912…`); any other international number as `00…`; the connection's outbound
prefix in front of every outside number.

## The incoming-call popup (2.23.0)

A `CallNotification` is written when a call rings a mapped extension
(`ringing`) and, when an inbound call is missed, for every mapped extension
that rang (`missed`) — only on a connection whose «پنجرهٔ تماس ورودی» is on.
A page of someone with such an extension carries `data-call-popup="1"` and
polls `GET telephony/notifications/` every two seconds while the tab is visible
(never while hidden; a failing server is asked less and less often; its own
throttle, 240 a minute). The inbox is one indexed query: undismissed rows of
the last 12 hours, a ringing one only while its call is still open.

Each new popup's details are fetched once, `GET telephony/notifications/<id>/`,
for the reader: the matched person *within the reader's scope* — name, avatar,
subtitle and the profile cards they may see (a customer's «بدهکاری», «مجموع
خرید», «امتیاز»; a colleague's «امتیاز») — else «مخاطب ثبت‌شده، خارج از محدودهٔ
شما» with the number only; «ثبت مشتری» (opens the new-customer form with the
number filled in) for an unknown number when the reader holds
`customers.manage`; «تماس دوباره» on a missed call for someone who can place
calls. `POST telephony/notifications/<id>/dismiss/` closes one. The popup is the
theme's toast, stacked under the header.

## What a call does to the rest of Dolphin (2.23.0)

`telephony/hooks.py`, registered as domain-event handlers and a signal
receiver, so the listener never calls into another module directly:

- **Missed call** (`call.missed`): the popups above, and — when the connection's
  «ساخت وظیفه برای تماس بی‌پاسخ مشتری» is on and the caller is a known
  customer — one follow-up task (`source = missed_call`, due in two hours),
  for whoever holds that customer's newest open lead, else the marketer who
  entered the customer, else the user whose extension rang. Idempotent per
  call.
- **Ended call** (`call.ended`): the customer's and the user's scores are
  refreshed.
- **Timelines**: calls are a *pull* source of both profile timelines, read
  through the reader's own `calls_for` — a reader sees exactly the calls they
  may see. «آخرین تعامل» follows from the timeline.
- **Scores**: a completed PBX call counts toward a customer's recency and
  engagement; the user factor «پیگیری تماس‌های بی‌پاسخ» (weight 10) is the share
  of missed inbound calls that rang them which were followed up within 24
  hours — they called the number back from the PBX, or the missed-call task
  for it was completed. A missed call younger than 24 hours with no follow-up
  yet has no verdict.
- **Profiles**: the customer «تماس‌ها» tab shows the PBX's calls beside the
  logged ones (each half behind its own permission); users get a «تماس‌ها» tab
  (their own with `calls.own`, anyone's with `calls.company`) with their
  extensions; «تماس» and the header phone place the call through the PBX for
  someone who can, and stay a `tel:` link otherwise; «عملکرد» shows the
  period's call figures (`GET telephony/stats/`). A contact is named in a call
  list only when the reader may open that person.

## API

| Method and path | Who | Notes |
|---|---|---|
| `GET calls/` | `calls.own` / `calls.company` | newest first, paginated; filters `person_type` + `person_id`, `user`, `status`, `direction`; `has_recording` is true only for a reader with `calls.recordings`; `person_display`/`person_url` only for a person the reader may open |
| `GET calls/{id}/recording/` | `calls.recordings`, call in scope | audio stream; 404 when the recording cannot be reached |
| `GET/POST telephony/extensions/` | Platform Admin | map a number to a user; 409 on a duplicate number or a second active extension for the user |
| `PATCH/DELETE telephony/extensions/{id}/` | Platform Admin | remapping and removal are audited; past calls keep their data |
| `POST telephony/originate/` | `calls.originate` + own extension | 202 with the request; see «Click-to-call» |
| `GET telephony/originate/{id}/` | the requester | `pending`, `sending`, `sent` or `failed` + `error` |
| `GET telephony/notifications/` | anyone | the reader's own popups now: `[{id, kind, open, status}]` |
| `GET telephony/notifications/{id}/` | its owner | what the popup shows, for the reader |
| `POST telephony/notifications/{id}/dismiss/` | its owner | 204 |
| `GET telephony/stats/?user=&period_start=&period_end=` | `calls.company`, or `calls.own` for oneself | inbound, answered, missed, outbound, talk time, average, missed followed up / decided |

All behind feature `telephony`; the extension writes use the sensitive throttle.

## Webhook PBXs (2.30.0)

A second connection kind, `pbx_webhook` (`telephony/pbx_webhook.py`), for a PBX
that *pushes* call events instead of exposing AMI. Per-brand set-up is in
`docs/ops/PBX_CONNECTION_GUIDES.md`.

- **Inbound.** `POST /api/v1/integrations/<id>/webhook/`, authenticated only by
  `verify_inbound`: `X-Signature` (base64 HMAC-SHA256 of the raw body),
  `X-Dolphin-Signature: sha256=<hex>`, or the shared key as `X-Dolphin-Token` /
  `?token=`. `telephony/vendors.py` turns the body into `CallEvent`s
  (`generic`, `yeastar`, `grandstream`, `freeswitch`); `telephony/ingest.py`
  applies them to `Call` with the same rules as the AMI tracker (create or update
  under `select_for_update`, never reopen a finished call, `call.started` /
  `.answered` / `.ended` / `.missed` events, popup, missed-call task, recording).
  Extension and outside-number classification reuses `CallTracker`. A body the
  chosen vendor cannot parse is a 400 (the receipt rolls back so a corrected
  retry is accepted). The generic format's id key is `call_id`, never `id`
  (the view uses `id` as the idempotency key).
- **Outbound (click-to-call).** `dial_mode` `yeastar` (OpenAPI `get_token` +
  `call/dial`) or `http` (URL and JSON template with `{extension}`/`{number}`).
  `request_originate` queues an `OriginateRequest` as for Asterisk; for
  `pbx_webhook` it then calls `dial_over_http` after commit, which claims
  PENDING→SENDING once, calls `telephony/dialer.place_call` (8 s timeout, no secret
  in any message) and marks SENT or FAILED. A returned PBX call id creates the
  outbound `Call` so later events land on it. A `pbx_webhook` connection with
  `dial_mode` `none` does not count as an originating extension, so the button
  does not appear for it.
- **Presets.** `Provider.presets` (also in `describe()`) carries ready values
  for the Asterisk family (FreePBX, Issabel/Elastix, VitalPBX, plain Asterisk);
  the connection form fills only non-secret fields from them.
- **Honesty.** Vendor payloads come from public documentation, not a real
  system; `vendors.VERIFIED` is empty and «آزمایش اتصال» says so.
- **Tests.** `telephony/tests/test_pbx_webhook.py`.

## Configuring a connection

On «یکپارچه‌سازی‌ها» → «افزودن اتصال» → «مرکز تلفن Asterisk / FreePBX»:

| Field | Meaning |
|---|---|
| AMI host, port, username, password | the AMI user below; the password is encrypted (`DOLPHIN_SECRETS_KEY`) |
| internal extension max length | a number this short, or a mapped extension, is internal (default 5) |
| outbound prefix | a digit the PBX needs before an outside number, if any |
| originate context, channel pattern, timeout, caller ID | how click-to-call rings the user's phone first; the pattern must contain `{extension}`; with no caller ID the user's phone shows the number being called |
| CDR host, port, database, table, username, password | the read-only CDR user below; leave the host empty to skip CDR sync |
| recordings mode, path, base URL, username, password | `none`, `mount` or `url`, as above |
| PBX time zone | for CDR `calldate` |
| missed-call task, call popup | per-connection switches for the follow-up task and the popup |

«آزمایش اتصال» logs in to AMI, pings, and — when CDR is configured — reads one
CDR row, and reports which part failed. Then map extensions under «داخلی‌های
تلفن».

## What the PBX administrator provides

1. An AMI user for Dolphin in `/etc/asterisk/manager_custom.conf` (FreePBX) or
   `manager.conf`, reachable from the Dolphin host only:

   ```ini
   [dolphin]
   secret = <long random password>
   deny = 0.0.0.0/0.0.0.0
   permit = <Dolphin host IP>/255.255.255.255
   read = call,cdr,agent
   write = originate
   writetimeout = 5000
   ```

   then `asterisk -rx "manager reload"`. Port 5038/TCP open from the Dolphin
   host only. (`write = originate` is needed only for click-to-call.)
2. A read-only CDR user on the PBX's MariaDB, from the Dolphin host only:

   ```sql
   CREATE USER 'dolphin_cdr'@'<Dolphin host IP>' IDENTIFIED BY '<password>';
   GRANT SELECT ON asteriskcdrdb.cdr TO 'dolphin_cdr'@'<Dolphin host IP>';
   ```

   and port 3306/TCP open from the Dolphin host only.
3. Recordings, one of: a read-only NFS/SSHFS export of
   `/var/spool/asterisk/monitor` to the Dolphin host, or an HTTPS endpoint that
   serves those files to the Dolphin host only.
4. The list of extensions and who sits at each.

## Tests

No PBX is needed: `telephony/tests/fake_ami.py` is a fake AMI server
(login, ping, originate, event push, dropped connections), recorded event
fixtures in `telephony/tests/fixtures/` cover inbound answered and missed,
outbound answered and busy, a transfer and a queue, and the CDR tests use
in-memory rows (duplicates, gaps, corrections).
