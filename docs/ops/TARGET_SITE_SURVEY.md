# Target site survey (phase P0R.1)

Fill this in before any deployment design is finalised. Every field is
currently **unanswered**; the reported values in `KARIZ_PROJECT_HANDOFF.md` §10
are customer claims, not verified facts, and must not be designed against.

This phase is `BLOCKED_EXTERNAL`: it needs answers from the customer and the
infrastructure owner. It does not block P1, P2, or P4, but P14 and P15 cannot
start without it.

**Never paste a password, key, certificate, or connection string into this
file.** Record hostnames, versions, models, and owners only. If a command's
output contains a licence key or serial number, redact it before sharing.

## 1. Host operating system — the single most important item

The customer reports "Windows Server 2008" on the Parand host. That phrase is
ambiguous and has three very different meanings. Resolve it first.

Run on the target host and paste the output:

```text
winver
```

```text
systeminfo
```

If PowerShell is available, this is more precise and easier to redact:

```powershell
Get-ComputerInfo -Property OsName, OsVersion, OsBuildNumber, OsArchitecture, CsName, WindowsProductName, OsServicePackMajorVersion
```

| Question | Answer |
|---|---|
| Does "2008" refer to the Windows Server edition, the SQL Server version, or the accounting software version? | |
| Exact `winver` version and build | |
| Windows edition (Standard / Enterprise / Datacenter / Foundation) | |
| Service Pack level | |
| Architecture (x86 / x64) | |
| Physical or already virtualised? | |
| Can the host run Hyper-V or another hypervisor? | |
| Total RAM and free disk (reported: 16 GB / ~2 TB SSD) | |

**Decision gate:** Windows Server 2008 and 2008 R2 are out of vendor support
and are not an accepted production target. If the evidence confirms 2008/2008
R2, the deployment cannot proceed on that OS. Two supported paths exist:

- **Path 1 — dedicated appliance/server:** a separate supported machine
  (Linux host recommended, since the application image is `linux/amd64`) used
  only for Kariz CRM.
- **Path 2 — OS upgrade:** upgrade the existing host to a supported Windows
  Server release with a container/virtualisation layer.

| Question | Answer |
|---|---|
| Which path is approved? | |
| Who pays for and owns the hardware/licence? | |

## 2. Co-hosted software constraints

| Question | Answer |
|---|---|
| Which accounting software runs on this host, and which version? | |
| What other application(s) run on it? | |
| Do any of them require a specific OS version, blocking an upgrade? | |
| Do any of them already bind ports 80, 443, 5432, or 8000? | |
| Is a maintenance window available, and when? | |

## 3. Network and routing

| Question | Answer |
|---|---|
| Tehran router brand / model / firmware version | |
| Parand router brand / model / firmware version | |
| Does each router support IPsec (or WireGuard) site-to-site VPN? | |
| Tehran public IP — static confirmed? | |
| Parand public IP — static confirmed? | |
| ISP name at each site, and any CGNAT or port-blocking in effect | |
| Internal subnet ranges at each site (must not overlap for site-to-site VPN) | |
| Uplink bandwidth at Parand (the server side) | |

Intended design, to be confirmed against the answers above: a router-to-router
site-to-site VPN carrying HTTPS, with individual VPN peers reserved for
management and for staff genuinely working outside the Tehran office.
PostgreSQL, the application port, Django Admin, SSH, RDP, container management,
and backup services are never published publicly.

## 4. Naming and certificates

| Question | Answer |
|---|---|
| Is there an Active Directory domain? If so, its name | |
| Is there a public internet domain for this system? | |
| Who owns/controls DNS, and can they create records on request? | |
| Internal hostname to be used for the application | |
| Will TLS use a public CA certificate or an internal/private CA? | |
| If internal CA: who distributes the trust root to client machines? | |

A private-network-only deployment can still use a real certificate, but the
chosen approach changes both the TLS runbook and the client rollout.

## 5. Users and load

| Question | Answer |
|---|---|
| Total number of application accounts expected in year one | |
| Peak number of simultaneously active users | |
| Number of marketers/sales agents (each needs an individual account) | |
| Are any users outside the Tehran office, now or planned? | |
| Expected sales/interaction records per day | |

Shared accounts are prohibited by decision, so the account count must equal the
headcount.

## 6. Power, endpoint security, and physical access

| Question | Answer |
|---|---|
| Is the Parand host on a UPS? Model and tested runtime | |
| Is there a generator or only battery backup? | |
| Antivirus / EDR product in use on the host | |
| Will antivirus exclusions be needed for the database/container directories? | |
| Who has physical access to the machine? | |
| Is the host in a locked room or rack? | |

## 7. Backup, restore, and ownership

| Question | Answer |
|---|---|
| Off-site backup destination (device, service, or location) | |
| Always-on Tehran destination for a second copy | |
| Available free space at each destination | |
| Required RPO (maximum acceptable data loss) | |
| Required RTO (maximum acceptable downtime) | |
| Backup retention period | |
| Who owns routine backup verification? | |
| Who is authorised to perform a restore? | |
| Who is the first-line incident contact, and what are their working hours? | |
| Who approves a maintenance window? | |

Backup and restore ownership must be a named person, not a role in the
abstract. `docs/ops/BACKUP_RESTORE.md` describes the mechanism; this table
records who is accountable for running it.

## 8. Commercial and support policy

| Question | Answer |
|---|---|
| Agreed support hours and response times | |
| Update/upgrade policy and who authorises a version change | |
| Is the source-protection and confidentiality contract signed? | |
| Who at the customer signs UAT acceptance? | |

## Completion

This survey is complete when every table above is filled and the OS decision
gate in section 1 has an approved path. Record the outcome in
`KARIZ_PROJECT_HANDOFF.md` §10 and §14, replacing the current unverified
claims with verified facts. Then P14 (real network/TLS/VPN build-out) may start.
