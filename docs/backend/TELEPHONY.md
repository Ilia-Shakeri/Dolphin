# Telephony — the Asterisk / FreePBX connector

Since 2.22.0 Dolphin can connect to an Asterisk PBX (plain Asterisk or
FreePBX) as a provider of the [integrations framework](INTEGRATIONS.md). Calls
are read live over the Asterisk Manager Interface (AMI), matched to a customer
or a colleague, stored as `telephony.Call` rows, corrected from the PBX's own
call records (CDR), and their recordings are played through Dolphin. The
product decisions behind it are D10–D14 and D20 in
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
- `CallNotification` — the per-user popup queue (used from 2.23.0).
- `CdrSyncState` — the CDR cursor and last error per connection.

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

## API

| Method and path | Who | Notes |
|---|---|---|
| `GET calls/` | `calls.own` / `calls.company` | newest first, paginated; filters `person_type` + `person_id`, `user`, `status`, `direction`; `has_recording` is true only for a reader with `calls.recordings` |
| `GET calls/{id}/recording/` | `calls.recordings`, call in scope | audio stream; 404 when the recording cannot be reached |
| `GET/POST telephony/extensions/` | Platform Admin | map a number to a user; 409 on a duplicate number or a second active extension for the user |
| `PATCH/DELETE telephony/extensions/{id}/` | Platform Admin | remapping and removal are audited; past calls keep their data |

All behind feature `telephony`; the extension writes use the sensitive throttle.

## Configuring a connection

On «یکپارچه‌سازی‌ها» → «افزودن اتصال» → «مرکز تلفن Asterisk / FreePBX»:

| Field | Meaning |
|---|---|
| AMI host, port, username, password | the AMI user below; the password is encrypted (`DOLPHIN_SECRETS_KEY`) |
| internal extension max length | a number this short, or a mapped extension, is internal (default 5) |
| outbound prefix | a digit the PBX needs before an outside number, if any |
| originate context, channel pattern, timeout, caller ID | how click-to-call rings the user's phone first (2.23.0); the pattern must contain `{extension}` |
| CDR host, port, database, table, username, password | the read-only CDR user below; leave the host empty to skip CDR sync |
| recordings mode, path, base URL, username, password | `none`, `mount` or `url`, as above |
| PBX time zone | for CDR `calldate` |
| missed-call task, call popup | per-connection switches for the 2.23.0 hooks |

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
