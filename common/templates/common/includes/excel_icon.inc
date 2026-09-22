{% comment %} The small icon on every Excel export/import button in the panel
   (customers, products, users, leads target audience, and every report's
   «خروجی اکسل»). Keenicons ships no Excel-branded glyph (checked: no
   spreadsheet-logo icon exists in the purchased duotone/outline/solid sets),
   and the product owner's own direction here (2026-09-21, then reaffirmed
   2026-09-22) is a small icon consistent with the panel's theme rather than a
   literal borrowed brand mark — so this is a small first-party SVG, styled
   like a spreadsheet document instead of Metronic's generic `ki-file-sheet`,
   not a copy of Microsoft's logo. Update every call site together if this
   ever changes; it is intentionally one file, not copied per page. {% endcomment %}
<svg class="excel-icon me-1" width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false"><path d="M6 2.5h8.5L19 7v13.5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1Z" fill="#1E7145"/><path d="M14.5 2.5V6a1 1 0 0 0 1 1H19L14.5 2.5Z" fill="#2BA36C"/><rect x="7.25" y="10" width="9.5" height="7.5" rx="0.75" fill="#fff" fill-opacity="0.95"/><path d="M7.25 12.6h9.5M7.25 15h9.5M11 10v7.5M13.25 10v7.5" stroke="#1E7145" stroke-width="0.65"/></svg>
