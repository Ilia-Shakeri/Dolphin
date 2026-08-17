# Kariz branding on the active path

Status: repository-controlled slice complete; real browser and edge-runtime proof pending.

## Approved active brand

- Product mark: `ForooshBin` / `فروش‌بین`.
- Persian admin header: `مدیریت فروش‌بین`.
- Persian admin index title: `پنل مدیریت فروش‌بین`.

## Active-path manifest

| Active path | Brand surface | Guard |
|---|---|---|
| `common/templates/common/home.html` | Page title, mark, and Persian product summary | Render test checks Kariz and rejects visible vendor names/external links |
| `common/admin.py` | Django admin header, browser title, and index title | Exact admin setting/render tests |
| `config/settings.py` | Schema title remains `ForooshBin API` | Schema validation |
| `common/static/common/kariz.css` | Project-owned visual shell with no remote brand asset | Static finder and collectstatic dry run |

The active home page contains no purchase, preview, demo, remote image, remote font, or vendor link. It does not rename framework/theme runtime identifiers because none are used by this shell.

## Surface applicability matrix

| Goal surface | Current active state | Brand proof or boundary |
|---|---|---|
| Root HTML title and body | Present at `/` | Exact Kariz/Persian render assertions |
| Login page | No custom CRM HTML login exists; authentication is the same-origin API. Django admin login is present | Admin login render asserts Persian RTL and Kariz header |
| Navigation and footer | No first-party navigation or footer exists in the current shell | Home source/render test proves no hidden demo action or external link |
| Django admin | Present | `common/admin.py` owns the three exact Kariz strings; render test covers the login surface |
| OpenAPI | Available only outside production | `config/settings.py` owns `ForooshBin API`; schema validation covers it; production does not map schema/docs routes |
| Email templates | No first-party email template or email-sending feature exists | Not applicable; add a branded template and test if an approved email feature is introduced |
| Logo, favicon, remote image, or remote font | No **remote** asset is referenced. Since the ForooshBin rebrand the shell serves one local favicon, `common/static/common/favicon.ico`, from the application's own static directory | Local-template and link scan proof; `common/tests/test_static_assets.py` |
| Operator/user documentation and runtime metadata | Current first-party operations docs, Dockerfile, Compose, and environment example are in the bounded brand scan | No vendor brand/domain match outside the two intentional negative test fixtures |

Brand ownership stays at each framework boundary: the home template owns its visible mark, Django admin owns admin strings, and schema settings own the API title. A shared runtime theme/config layer does not exist, so adding one only to remove these three small explicit boundaries would add needless coupling. Exact tests keep the values aligned.

## Residual term and action matrix

| Path or scope | Residual/action | Reason and visibility |
|---|---|---|
| Active rendered home/admin/schema | No vendor term, purchase/preview/demo link, remote asset, fake action, or vendor upload endpoint found | User-visible source is clean |
| `common/tests/test_ui.py:16` | `Metronic` remains in a negative assertion | Test-only guard; never rendered or shipped as product branding |
| `common/tests/test_ui.py:17` | `KeenThemes` remains in a negative assertion | Test-only guard; never rendered or shipped as product branding |
| `docs/codebase/BRANDING_CLEANUP.md` | Vendor terms appear only in this internal evidence/exception record | Required audit evidence; not a served product surface |
| Excluded static archive and required notices | Not scanned, renamed, or deleted | Outside the served/image path; unknown external use and legal notices forbid blind cleanup |

## Archive and notice boundary

The excluded static archive may still contain demo/vendor brand text and legally required third-party notices. It is outside the active Django template/static path and backend image, and no archive file was edited or deleted. Residual archive text is not claimed as cleaned. A future external deployment that serves the archive must be mapped and tested before its brand state can be claimed.

Required third-party framework resources and notices remain intact. No blind text replacement was run.

## Evidence and limits

- Evidence checkpoint: 2026-08-09, Goal checkpoint 004.
- `python manage.py test common.tests.test_ui --settings=config.test_settings -v 1`: 4 passed.
- Full fast suite: 177 passed.
- OpenAPI schema validation and static dry run pass.
- Bounded active brand-term scan found only the two intentional negative assertions named above.
- Bounded served-source link scan found no HTTP(S), purchase, preview, demo, or vendor-upload target.
- Reproducible bounded scans:

```powershell
rg -n -i 'Metronic|KeenThemes|Keen Themes|keenthemes\.com|preview\.keenthemes\.com|devs\.keenthemes\.com' -- accounts auditlog common config reports sales docs/ops Dockerfile compose.yml .env.example
rg -n -i 'https?://|purchase|preview|demo|vendor.*upload' -- common/templates common/static common/admin.py common/ui_views.py config/settings.py
```

The first scan returns only `common/tests/test_ui.py:16-17`; the second returns no match.
- No real browser visual, responsive, link, console/network, Docker, or Nginx smoke ran on this host.
