# Persian-only active path

Status: repository-controlled slice complete; real browser and edge-runtime proof pending.

## Scope

Only the active first-party Django surfaces were reviewed and changed. No excluded archive, vendor, minified, media, font, binary, dependency, generated, or cache tree was inspected or edited.

| Active path | Language role | Evidence |
|---|---|---|
| `config/settings.py` | Default language is `fa` | Settings and UI tests |
| `config/urls.py` | Serves the first-party root shell and Django admin | URL check and render tests |
| `common/ui_urls.py` | Owns only `/` | Root response test |
| `common/ui_views.py` | Renders the fixed home template | Root response test |
| `common/templates/common/home.html` | Declares `lang="fa"` and `dir="rtl"`; visible copy is Persian except the approved product mark | Exact content tests |
| `common/admin.py` | Gives Django admin Persian Kariz headers | Admin render test |
| `common/static/common/kariz.css` | Local RTL-safe presentation; no remote asset | Static finder and collectstatic dry run |
| `common/tests/test_ui.py` | Guards language, RTL, local asset, and admin output | Full suite |

## Active behavior

- `/` is a small first-party Kariz shell. It contains no language selector, locale cookie/query behavior, demo action, or external link.
- Django admin renders with Persian framework translations and RTL styles because the default language is `fa`.
- No project-owned active locale directory or non-Persian translation bundle is referenced by this shell.
- Programming-language identifiers, API/database names, machine-readable report headers, and required framework resources are not user locale choices and remain unchanged.

## Action and exception matrix

| Area | Current source result | Action or justified exception |
|---|---|---|
| Project-owned locale files | No `locale`, `locales`, `lang`, `languages`, `i18n`, or `l10n` tree and no `.po`/`.mo` file exists in the active first-party apps | No file removed because no active deletion candidate exists |
| Language selector UI | No selector, switch control, flag control, or language form exists on `/` or Django admin customization | No selector removed because none exists |
| Language state behavior | No `LocaleMiddleware`, `set_language`, `i18n_patterns`, project `LANGUAGES` list, language cookie/query key, or local-storage handler exists in the active first-party apps | No handler, route, field, cookie, or selector removed because none exists |
| Default locale and direction | `config/settings.py` sets `LANGUAGE_CODE = "fa"`; the home template fixes `lang="fa"` and `dir="rtl"`; Django admin inherits Persian/RTL behavior | Keep the explicit Persian default and render guards |
| First-party active static | `common/static/common/kariz.css` is the only project-owned shell asset and contains no locale payload or remote import | Keep as local RTL-safe presentation |
| Django dependency locales | Dependency-owned Django locale data such as `django/conf/locale/**` and Django admin translation/RTL/static resources remain installed | Required framework exception; these files are not project-owned language choices and must not be edited or deleted from installed dependencies |
| Machine and developer text | Python, API/database identifiers, stable report headers, and technical operator documentation remain language-stable | Required non-UI exception under the Persian-only policy |
| Excluded static archive | Not in `TEMPLATES.DIRS`, backend image, or repository URL map | Leave untouched; unknown external use and any deletion need a separate manifest and runtime proof |

## Archive boundary

The separate static template archive is not referenced by `TEMPLATES.DIRS`, is excluded from the backend image, and is not served by the repository-controlled URL map. It remains untouched. No locale file was deleted. This current-stack proof is not permission to delete the archive: any later deletion still needs an exact manifest, reference proof, a safe Git baseline, and browser/static regression checks.

## Evidence and limits

- Evidence checkpoint: 2026-08-09, Goal checkpoint 004.
- Bounded active-file locale-resource scan: no project-owned locale file or directory matched.
- Bounded language-state scan: no switch, route, cookie, query, storage, middleware, or project locale-list behavior matched.
- `python manage.py test common.tests.test_ui --settings=config.test_settings -v 1`: 4 passed.
- `python manage.py test --settings=config.test_settings -v 1`: 177 passed.
- `python manage.py check --settings=config.test_settings`: clean.
- `python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0`: clean.
- Reproducible bounded scans:

```powershell
$activeFiles = rg --files accounts auditlog common config reports sales
$activeFiles | rg '(^|[\\/])(locale|locales|lang|languages|i18n|l10n)([\\/]|$)|\.(po|mo)$'
rg -n -i 'LocaleMiddleware|set_language|i18n_patterns|LANGUAGES\s*=|language[_-]?(switch|selector|cookie)|localStorage.*lang|\?lang=' -- accounts auditlog common config reports sales
```

Both scans return no match. A no-match result is the expected proof, not a failed cleanup command.
- Source/render tests prove the active repository output. No real browser, responsive viewport, console/network, Docker, or Nginx UI smoke ran on this host.
