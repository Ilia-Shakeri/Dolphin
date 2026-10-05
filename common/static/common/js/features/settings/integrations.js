import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {bindDecimalInput} from "dolphin/core/decimal.js";
import {apiDateTime, displayDate} from "dolphin/core/jalali.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {setupProfileTabs} from "dolphin/ui/profile-tabs.js";
import {appendCell, pageRangeLabel} from "dolphin/ui/table.js";

/**
 * The «اتصال سرویس‌ها» page: one card per integration, each with a real
 * test where a real test exists.
 *
 * Everything on that page is server-rendered from
 * `common/integrations.py` — the list, the status badge, the masked key,
 * the last error. The only thing that needs script is the test button,
 * and it does no more than post to the URL that row declared and print
 * what came back. A row with no `data-integration-test` has no button,
 * because an integration this build cannot really test should not offer
 * a control that pretends otherwise.
 */
/**
 * «یکپارچه‌سازی‌ها» — the framework half of the page (2.21.0). Rendered
 * only for a Platform Admin where `integrations` runs; every endpoint
 * checks both again. Connection forms are built from each provider's own
 * field list (`#integration-catalog`); secrets are write-only — a blank
 * secret field keeps what is stored, and nothing secret is ever read back.
 */
//: The post carrier's connection is the «سرویس پست» row above the table
//: (2.40.7, `common/integrations.py`), not a second entry of its own: it is
//: left out of the connections table and of the «افزودن اتصال» catalog, and
//: that row's «ویرایش اتصال» opens this editor (`?edit=ebazar_post`).
const POST_PROVIDER = "ebazar_post";

function setupIntegrationFramework() {
    const catalogNode = document.getElementById("integration-catalog");
    if (!catalogNode) return;
    const catalog = JSON.parse(catalogNode.textContent);
    const providersByKey = Object.fromEntries(catalog.providers.map((provider) => [provider.key, provider]));
    const STATUS_ACCENT = {ok: "success", error: "danger", disabled: "secondary", unconfigured: "warning"};
    let integrations = [];
    // One tab per part of the framework (2.24.0); every list still loads
    // up front — they are small, and a row's «گزارش» jumps across tabs.
    const tabs = setupProfileTabs({});

    function wireDialog(dialog) {
        dialog?.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    }
    ["integration-catalog-dialog", "integration-dialog", "subscription-dialog", "token-dialog", "secret-once-dialog", "extension-dialog"].forEach((id) => wireDialog(document.getElementById(id)));

    function showOnce(value, note) {
        const dialog = document.getElementById("secret-once-dialog");
        document.getElementById("secret-once-value").value = value;
        document.getElementById("secret-once-note").textContent = note;
        dialog.showModal();
        document.getElementById("secret-once-value").select();
    }
    document.getElementById("secret-once-copy")?.addEventListener("click", async () => {
        const field = document.getElementById("secret-once-value");
        field.select();
        try { await navigator.clipboard.writeText(field.value); globalMessage("رونوشت شد.", true); } catch { /* the value is selected; the reader copies it */ }
    });

    function toggle(checked, label, onChange) {
        const wrap = document.createElement("div");
        wrap.className = "form-check form-switch form-check-custom form-check-solid";
        const input = document.createElement("input");
        input.className = "form-check-input";
        input.type = "checkbox";
        input.checked = checked;
        input.setAttribute("aria-label", label);
        input.addEventListener("change", async () => {
            input.disabled = true;
            try { await onChange(input.checked); } catch (error) { input.checked = !input.checked; showError(error); } finally { input.disabled = false; }
        });
        wrap.appendChild(input);
        return wrap;
    }

    function button(label, className, handler) {
        const node = document.createElement("button");
        node.type = "button";
        node.className = `btn btn-sm ${className}`;
        node.textContent = label;
        node.addEventListener("click", () => handler(node));
        return node;
    }

    function listCard(prefix) {
        return {
            loading: document.getElementById(`${prefix}-loading`),
            empty: document.getElementById(`${prefix}-empty`),
            wrap: document.getElementById(`${prefix}-table-wrap`),
            body: document.getElementById(`${prefix}-table-body`),
            fill(rows) {
                this.body.replaceChildren(...rows);
                this.loading.hidden = true;
                this.empty.hidden = rows.length > 0;
                // The connections list shares its table with the
                // built-in services, so it has no wrapper to hide.
                if (this.wrap) this.wrap.hidden = rows.length === 0;
            },
        };
    }

    // --- connections -----------------------------------------------------
    const connections = listCard("integrations");
    const dialog = document.getElementById("integration-dialog");
    const form = document.getElementById("integration-form");
    const providerSelect = document.getElementById("integration-provider");
    const fieldsHost = document.getElementById("integration-fields");
    let editing = null;

    catalog.providers.forEach((provider) => {
        const option = document.createElement("option");
        option.value = provider.key;
        option.textContent = provider.name;
        providerSelect.appendChild(option);
    });

    function renderFields(provider, integration) {
        document.getElementById("integration-provider-description").textContent = provider ? provider.description : "";
        const extras = [];
        const presetNote = "قالب فقط مقدارهای غیرمحرمانه را پر می‌کند؛ گذرواژه‌ها را خودتان وارد کنید.";
        if (provider && provider.presets && provider.presets.length) {
            const column = document.createElement("div");
            column.className = "col-12";
            const label = document.createElement("label");
            label.className = "form-label fw-semibold";
            label.setAttribute("for", "integration-preset");
            label.textContent = "قالب آمادهٔ سامانه";
            const select = document.createElement("select");
            select.id = "integration-preset";
            select.className = "form-select form-select-solid";
            const none = document.createElement("option");
            none.value = "";
            none.textContent = "بدون قالب — خودم پر می‌کنم";
            select.appendChild(none);
            provider.presets.forEach((preset) => {
                const option = document.createElement("option");
                option.value = preset.key;
                option.textContent = preset.label;
                select.appendChild(option);
            });
            const note = document.createElement("p");
            note.className = "text-muted fs-8 mt-1 mb-0";
            note.textContent = presetNote;
            select.addEventListener("change", () => {
                const preset = provider.presets.find((row) => row.key === select.value);
                note.textContent = preset ? preset.note : presetNote;
                if (!preset) return;
                Object.entries(preset.values).forEach(([key, value]) => {
                    const input = fieldsHost.querySelector(`[name="${key}"]`);
                    if (!input || input.dataset.secret) return;
                    if (input.type === "checkbox") input.checked = Boolean(value);
                    else input.value = String(value);
                });
            });
            column.append(label, select, note);
            extras.push(column);
        }
        if (integration && integration.webhook_path) {
            const column = document.createElement("div");
            column.className = "col-12";
            const label = document.createElement("label");
            label.className = "form-label fw-semibold";
            label.textContent = "نشانی وب‌هوک (در مرکز تلفن بگذارید)";
            const input = document.createElement("input");
            input.className = "form-control form-control-solid";
            input.dir = "ltr";
            input.readOnly = true;
            input.value = `${window.location.origin}${integration.webhook_path}`;
            column.append(label, input);
            extras.push(column);
        }
        fieldsHost.replaceChildren(...extras, ...(provider ? provider.fields : []).map((field) => {
            const column = document.createElement("div");
            column.className = field.kind === "bool" ? "col-12 d-flex align-items-center gap-3" : "col-md-6";
            const id = `integration-field-${field.key}`;
            let input;
            if (field.kind === "select") {
                input = document.createElement("select");
                input.className = "form-select form-select-solid";
                field.choices.forEach((choice) => {
                    const option = document.createElement("option");
                    option.value = choice.value;
                    option.textContent = choice.label;
                    input.appendChild(option);
                });
            } else {
                input = document.createElement("input");
                input.className = field.kind === "bool" ? "form-check-input" : "form-control form-control-solid";
                input.type = {bool: "checkbox", url: "url", password: "password"}[field.kind] || (field.secret ? "password" : "text");
                if (field.kind === "int") {
                    // A whole number in any digits (2.40.14, `core/decimal.js`).
                    input.inputMode = "numeric";
                    input.dataset.decimalInput = "";
                    input.dataset.decimalPlaces = "0";
                    bindDecimalInput(input);
                }
                if (field.secret) input.autocomplete = "new-password";
                if (["url", "int", "password"].includes(field.kind) || field.secret || field.ltr) input.dir = "ltr";
            }
            input.id = id;
            input.name = field.key;
            input.dataset.secret = field.secret ? "true" : "";
            input.dataset.kind = field.kind;
            const stored = integration ? integration.config[field.key] : undefined;
            const initial = stored !== undefined ? stored : field.default;
            if (field.kind === "bool") input.checked = Boolean(initial);
            else if (!field.secret && initial !== null && initial !== undefined) input.value = String(initial);
            if (field.secret && integration && integration.secret_hints[field.key]) {
                input.placeholder = `${integration.secret_hints[field.key]} — خالی بماند یعنی تغییر نکند`;
            } else if (field.placeholder) {
                input.placeholder = field.placeholder;
            }
            const label = document.createElement("label");
            label.className = `form-label fw-semibold${field.kind === "bool" ? " mb-0" : ""}${field.required && !(field.secret && integration) ? " required" : ""}`;
            label.setAttribute("for", id);
            label.textContent = field.label;
            const error = document.createElement("p");
            error.className = "text-danger fs-8 mt-1 mb-0";
            error.dataset.errorFor = field.key;
            if (field.kind === "bool") {
                column.append(input, label, error);
            } else {
                column.append(label, input);
                if (field.help) {
                    const help = document.createElement("p");
                    help.className = "text-muted fs-8 mt-1 mb-0";
                    help.textContent = field.help;
                    column.appendChild(help);
                }
                column.appendChild(error);
            }
            return column;
        }));
    }

    function openConnection(integration = null, providerKey = "") {
        editing = integration;
        form.reset();
        clearMessages(form);
        const provider = providersByKey[integration ? integration.provider_key : providerKey];
        document.getElementById("integration-dialog-title").textContent = integration
            ? `ویرایش «${integration.name}»`
            : `افزودن اتصال${provider ? ` — ${provider.name}` : ""}`;
        providerSelect.disabled = Boolean(integration);
        if (provider) providerSelect.value = provider.key;
        document.getElementById("integration-name").value = integration ? integration.name : "";
        document.getElementById("integration-enabled").checked = integration ? integration.enabled : false;
        renderFields(providersByKey[providerSelect.value], integration);
        dialog.showModal();
    }

    providerSelect.addEventListener("change", () => renderFields(providersByKey[providerSelect.value], null));

    // «افزودن اتصال» opens the catalog first: what can be connected now
    // (the providers), the panel's own services (each on its own
    // settings page), and what is only planned — named, never pressable.
    const catalogDialog = document.getElementById("integration-catalog-dialog");
    const catalogHost = document.getElementById("integration-catalog-providers");
    catalog.providers.filter((provider) => provider.key !== POST_PROVIDER).forEach((provider) => {
        const column = document.createElement("div");
        column.className = "col-md-6";
        const card = document.createElement("button");
        card.type = "button";
        card.className = "btn btn-outline btn-outline-dashed btn-active-light-primary d-flex align-items-start text-start gap-4 p-5 w-100 h-100";
        card.dataset.provider = provider.key;
        const symbol = document.createElement("span");
        symbol.className = "symbol symbol-40px flex-shrink-0";
        symbol.innerHTML = '<span class="symbol-label bg-light-primary"><i class="di-duotone di-abstract-26 fs-2 text-primary" aria-hidden="true"><span class="path1"></span><span class="path2"></span></i></span>';
        const text = document.createElement("span");
        text.className = "min-w-0";
        const title = document.createElement("span");
        title.className = "d-block fw-bold text-gray-900";
        title.textContent = provider.name;
        const description = document.createElement("span");
        description.className = "d-block text-muted fs-8";
        description.textContent = provider.description;
        text.append(title, description);
        if (provider.capabilities.length) {
            const chips = document.createElement("span");
            chips.className = "d-flex flex-wrap gap-1 mt-2";
            provider.capabilities.forEach((capability) => {
                const chip = document.createElement("span");
                chip.className = "badge badge-light-primary fs-9";
                chip.textContent = capability.label;
                chips.appendChild(chip);
            });
            text.appendChild(chips);
        }
        card.append(symbol, text);
        card.addEventListener("click", () => {
            catalogDialog.close();
            openConnection(null, provider.key);
        });
        column.appendChild(card);
        catalogHost.appendChild(column);
    });
    document.getElementById("open-integration-catalog")?.addEventListener("click", () => catalogDialog.showModal());

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const config = {};
            const secrets = {};
            fieldsHost.querySelectorAll("[name]").forEach((input) => {
                if (input.dataset.secret) {
                    if (input.value) secrets[input.name] = input.value;
                } else if (input.dataset.kind === "bool") {
                    config[input.name] = input.checked;
                } else if (input.value !== "") {
                    config[input.name] = input.dataset.kind === "int" ? Number(input.value) : input.value;
                }
            });
            const body = {
                name: document.getElementById("integration-name").value,
                enabled: document.getElementById("integration-enabled").checked,
                config,
                secrets,
            };
            if (editing) {
                await apiRequest(`/api/v1/integrations/${editing.id}/`, {method: "PATCH", body});
            } else {
                await apiRequest("/api/v1/integrations/", {method: "POST", body: {...body, provider_key: providerSelect.value}});
            }
            dialog.close();
            globalMessage("اتصال ذخیره شد.", true);
            await loadConnections();
        });
    });

    function connectionRow(integration) {
        const row = document.createElement("tr");
        const name = document.createElement("td");
        // Same symbol-and-text cell as the built-in rows above it.
        const cell = document.createElement("div");
        cell.className = "d-flex align-items-start gap-3";
        const symbol = document.createElement("span");
        symbol.className = "symbol symbol-40px flex-shrink-0";
        symbol.innerHTML = `<span class="symbol-label bg-light-${STATUS_ACCENT[integration.status] || "secondary"}"><i class="di-duotone di-abstract-26 fs-2 text-${STATUS_ACCENT[integration.status] || "secondary"}" aria-hidden="true"><span class="path1"></span><span class="path2"></span></i></span>`;
        const text = document.createElement("div");
        text.className = "min-w-0";
        cell.append(symbol, text);
        name.appendChild(cell);
        const strong = document.createElement("span");
        strong.className = "d-block fw-semibold text-gray-900";
        strong.textContent = integration.name;
        text.appendChild(strong);
        if (integration.webhook_path) {
            const path = document.createElement("code");
            path.className = "d-block fs-8 text-muted integration-webhook-path";
            path.dir = "ltr";
            path.textContent = `${window.location.origin}${integration.webhook_path}`;
            path.title = "نشانی وب‌هوک ورودی این اتصال";
            text.appendChild(path);
        }
        row.appendChild(name);
        appendCell(row, integration.provider_name);
        const status = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = `badge badge-light-${STATUS_ACCENT[integration.status] || "secondary"}`;
        badge.textContent = integration.status_label;
        if (integration.last_error) badge.title = integration.last_error;
        status.appendChild(badge);
        if (integration.last_error) {
            const error = document.createElement("span");
            error.className = "d-block text-danger fs-8 mt-1 text-break";
            error.textContent = integration.last_error;
            status.appendChild(error);
        }
        row.appendChild(status);
        appendCell(row, integration.last_health_at ? displayDate(integration.last_health_at) : "");
        const enabled = document.createElement("td");
        enabled.appendChild(toggle(integration.enabled, `روشن بودن ${integration.name}`, async (value) => {
            await apiRequest(`/api/v1/integrations/${integration.id}/`, {method: "PATCH", body: {enabled: value}});
            await loadConnections();
        }));
        row.appendChild(enabled);
        const actions = document.createElement("td");
        actions.className = "row-actions";
        actions.append(
            button("ویرایش", "btn-light", () => openConnection(integration)),
            button("گزارش", "btn-light", () => {
                logFilter.value = String(integration.id);
                tabs?.activate("logs", {push: true});
                loadLogs(1);
            }),
            button("آزمایش اتصال", "btn-light-primary", async (node) => {
                node.disabled = true;
                clearMessages();
                try {
                    const result = await apiRequest(`/api/v1/integrations/${integration.id}/test/`, {method: "POST", body: {}});
                    globalMessage(result.message, result.ok);
                    await loadConnections();
                } catch (error) {
                    showError(error);
                } finally {
                    node.disabled = false;
                }
            }),
            button("حذف", "btn-light-danger", async (node) => {
                if (!await confirmDialog(`اتصال «${integration.name}» حذف شود؟ رمزهای ذخیره‌شده‌اش هم پاک می‌شوند.`)) return;
                node.disabled = true;
                try {
                    await apiRequest(`/api/v1/integrations/${integration.id}/`, {method: "DELETE"});
                    globalMessage("اتصال حذف شد.", true);
                    await loadConnections();
                } catch (error) {
                    node.disabled = false;
                    showError(error);
                }
            }),
        );
        row.appendChild(actions);
        return row;
    }

    const logFilter = document.getElementById("integration-logs-filter");

    async function loadConnections() {
        try {
            integrations = await apiRequest("/api/v1/integrations/");
            connections.fill(integrations.filter((integration) => integration.provider_key !== POST_PROVIDER).map(connectionRow));
            const chosen = logFilter.value;
            logFilter.replaceChildren(logFilter.options[0]);
            integrations.forEach((integration) => {
                const option = document.createElement("option");
                option.value = String(integration.id);
                option.textContent = integration.name;
                logFilter.appendChild(option);
            });
            logFilter.value = chosen;
        } catch (error) {
            connections.loading.hidden = true;
            showError(error);
        }
    }

    // --- log -------------------------------------------------------------
    const logs = listCard("logs");
    let logPage = 1;
    async function loadLogs(page = 1) {
        logs.loading.hidden = false;
        try {
            const query = new URLSearchParams({page: String(page)});
            if (logFilter.value) query.set("integration", logFilter.value);
            const data = await apiRequest(`/api/v1/integration-logs/?${query}`);
            logs.fill(data.results.map((entry) => {
                const row = document.createElement("tr");
                appendCell(row, displayDate(entry.created_at));
                appendCell(row, entry.direction_label);
                appendCell(row, entry.event_label);
                const result = document.createElement("td");
                const badge = document.createElement("span");
                badge.className = `badge badge-light-${entry.status === "ok" ? "success" : entry.status === "error" ? "danger" : "secondary"}`;
                badge.textContent = entry.status_label;
                result.appendChild(badge);
                row.appendChild(result);
                const message = appendCell(row, entry.message);
                message.className = "text-break";
                // A message from a number no customer has (2.24.0): the
                // server offers the create page, prefilled, only to a
                // reader who may create customers.
                if (entry.create_customer_url) {
                    const link = document.createElement("a");
                    link.className = "btn btn-sm btn-light-primary d-inline-block ms-2 mt-1";
                    link.href = entry.create_customer_url;
                    link.textContent = "ثبت مشتری";
                    message.appendChild(link);
                }
                return row;
            }));
            logPage = page;
            document.getElementById("logs-prev").disabled = !data.previous;
            document.getElementById("logs-next").disabled = !data.next;
            document.getElementById("logs-page-label").textContent = pageRangeLabel(data, page);
            document.getElementById("logs-pagination").hidden = !data.previous && !data.next;
        } catch (error) {
            logs.loading.hidden = true;
            showError(error);
        }
    }
    logFilter.addEventListener("change", () => loadLogs(1));
    document.getElementById("logs-prev").addEventListener("click", () => loadLogs(logPage - 1));
    document.getElementById("logs-next").addEventListener("click", () => loadLogs(logPage + 1));

    // --- outbound webhooks -------------------------------------------------------
    const subscriptionDialog = document.getElementById("subscription-dialog");
    const subscriptions = subscriptionDialog ? listCard("subscriptions") : null;
    const eventLabels = Object.fromEntries(catalog.event_types.map((item) => [item.key, item.label]));
    if (subscriptionDialog) {
        const events = document.getElementById("subscription-events");
        catalog.event_types.forEach((item) => {
            const label = document.createElement("label");
            label.className = "d-flex align-items-center gap-2";
            const box = document.createElement("input");
            box.type = "checkbox";
            box.className = "form-check-input";
            box.name = "event_types";
            box.value = item.key;
            label.append(box, item.label);
            events.appendChild(label);
        });
        const subscriptionForm = document.getElementById("subscription-form");
        document.getElementById("open-subscription-dialog").addEventListener("click", () => {
            subscriptionForm.reset();
            clearMessages(subscriptionForm);
            subscriptionDialog.showModal();
        });
        subscriptionForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(subscriptionForm, async () => {
                const data = new FormData(subscriptionForm);
                const created = await apiRequest("/api/v1/webhook-subscriptions/", {
                    method: "POST",
                    body: {name: data.get("name"), url: data.get("url"), event_types: data.getAll("event_types")},
                });
                subscriptionDialog.close();
                showOnce(created.secret, `کلید امضای وب‌هوک «${created.name}». گیرنده با آن سرآیند X-Dolphin-Signature را بررسی می‌کند.`);
                await loadSubscriptions();
            });
        });
    }

    async function loadSubscriptions() {
        if (!subscriptions) return;
        try {
            const rows = await apiRequest("/api/v1/webhook-subscriptions/");
            subscriptions.fill(rows.map((subscription) => {
                const row = document.createElement("tr");
                appendCell(row, subscription.name).className = "fw-semibold";
                appendCell(row, subscription.url).dir = "ltr";
                appendCell(row, subscription.event_types.length ? subscription.event_types.map((key) => eventLabels[key] || key).join("، ") : "همهٔ رویدادها");
                appendCell(row, subscription.secret_hint).dir = "ltr";
                const active = document.createElement("td");
                active.appendChild(toggle(subscription.active, `روشن بودن ${subscription.name}`, async (value) => {
                    await apiRequest(`/api/v1/webhook-subscriptions/${subscription.id}/`, {method: "PATCH", body: {active: value}});
                }));
                row.appendChild(active);
                const actions = document.createElement("td");
                actions.className = "row-actions";
                actions.append(
                    button("ارسال آزمایشی", "btn-light-primary", async (node) => {
                        node.disabled = true;
                        clearMessages();
                        try {
                            const result = await apiRequest(`/api/v1/webhook-subscriptions/${subscription.id}/ping/`, {method: "POST", body: {}});
                            globalMessage(
                                result.delivered
                                    ? `تحویل شد (پاسخ ${toPersianDigits(String(result.response_status))}).`
                                    : `تحویل نشد: ${result.error || "پاسخی نیامد"}`,
                                result.delivered,
                            );
                            await loadLogs(1);
                        } catch (error) {
                            showError(error);
                        } finally {
                            node.disabled = false;
                        }
                    }),
                    button("حذف", "btn-light-danger", async (node) => {
                        if (!await confirmDialog(`وب‌هوک «${subscription.name}» حذف شود؟`)) return;
                        node.disabled = true;
                        try {
                            await apiRequest(`/api/v1/webhook-subscriptions/${subscription.id}/`, {method: "DELETE"});
                            await loadSubscriptions();
                        } catch (error) {
                            node.disabled = false;
                            showError(error);
                        }
                    }),
                );
                row.appendChild(actions);
                return row;
            }));
        } catch (error) {
            subscriptions.loading.hidden = true;
            showError(error);
        }
    }

    // --- API tokens -------------------------------------------------------------
    const tokenDialog = document.getElementById("token-dialog");
    const tokens = tokenDialog ? listCard("tokens") : null;
    if (tokenDialog) {
        const tokenForm = document.getElementById("token-form");
        document.getElementById("open-token-dialog").addEventListener("click", () => {
            tokenForm.reset();
            clearMessages(tokenForm);
            tokenDialog.showModal();
        });
        tokenForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(tokenForm, async () => {
                const data = new FormData(tokenForm);
                const typed = String(data.get("expires_at") || "").trim();
                const expires = typed ? apiDateTime(typed) : "";
                if (typed && !expires) throw new Error("تاریخ انقضا خوانده نشد؛ قالب باید ۱۴۰۵/۰۵/۲۵ ۱۴:۳۰ باشد.");
                const created = await apiRequest("/api/v1/api-tokens/", {
                    method: "POST",
                    body: {name: data.get("name"), user: Number(data.get("user")), scopes: data.getAll("scopes"), expires_at: expires},
                });
                tokenDialog.close();
                showOnce(created.token, `توکن «${created.name}». در سرآیند Authorization: Bearer بفرستید.`);
                await loadTokens();
            });
        });
    }

    async function loadTokens() {
        if (!tokens) return;
        try {
            const rows = await apiRequest("/api/v1/api-tokens/");
            tokens.fill(rows.map((token) => {
                const row = document.createElement("tr");
                appendCell(row, token.name).className = "fw-semibold";
                appendCell(row, token.user_display);
                appendCell(row, `${token.prefix}…`).dir = "ltr";
                appendCell(row, token.scopes.map((scope) => ({read: "خواندن", write: "نوشتن"}[scope] || scope)).join("، "));
                appendCell(row, token.last_used_at ? displayDate(token.last_used_at) : "");
                const state = document.createElement("td");
                const badge = document.createElement("span");
                const expired = token.expires_at && new Date(token.expires_at) <= new Date();
                badge.className = `badge ${token.revoked_at || expired ? "badge-light-danger" : "badge-light-success"}`;
                badge.textContent = token.revoked_at ? "باطل‌شده" : expired ? "منقضی" : "فعال";
                state.appendChild(badge);
                row.appendChild(state);
                const actions = document.createElement("td");
                if (!token.revoked_at) {
                    actions.appendChild(button("باطل کردن", "btn-light-danger", async (node) => {
                        if (!await confirmDialog(`توکن «${token.name}» باطل شود؟ هر سامانه‌ای که با آن کار می‌کند فوراً قطع می‌شود.`)) return;
                        node.disabled = true;
                        try {
                            await apiRequest(`/api/v1/api-tokens/${token.id}/revoke/`, {method: "POST", body: {}});
                            await loadTokens();
                        } catch (error) {
                            node.disabled = false;
                            showError(error);
                        }
                    }));
                }
                row.appendChild(actions);
                return row;
            }));
        } catch (error) {
            tokens.loading.hidden = true;
            showError(error);
        }
    }

    // --- telephony extensions (2.22.0) ------------------------------------------
    const extensionDialog = document.getElementById("extension-dialog");
    const extensions = extensionDialog ? listCard("extensions") : null;
    let editingExtension = null;
    function pbxConnections() {
        return integrations.filter((integration) => ["asterisk", "pbx_webhook"].includes(integration.provider_key));
    }
    if (extensionDialog) {
        const extensionForm = document.getElementById("extension-form");
        const pbxSelect = document.getElementById("extension-integration");
        function openExtension(extension = null) {
            const pbx = pbxConnections();
            if (!pbx.length) {
                globalMessage("اول یک اتصال «مرکز تلفن Asterisk / FreePBX» بسازید.", false);
                return;
            }
            editingExtension = extension;
            extensionForm.reset();
            clearMessages(extensionForm);
            pbxSelect.replaceChildren(...pbx.map((integration) => {
                const option = document.createElement("option");
                option.value = String(integration.id);
                option.textContent = integration.name;
                return option;
            }));
            document.getElementById("extension-dialog-title").textContent = extension ? `ویرایش داخلی ${toPersianDigits(extension.number)}` : "افزودن داخلی";
            if (extension) {
                pbxSelect.value = String(extension.integration);
                document.getElementById("extension-number").value = extension.number;
                document.getElementById("extension-user").value = extension.user ? String(extension.user) : "";
                document.getElementById("extension-label").value = extension.label;
                document.getElementById("extension-active").checked = extension.active;
            }
            extensionDialog.showModal();
        }
        document.getElementById("open-extension-dialog").addEventListener("click", () => openExtension());
        extensionForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(extensionForm, async () => {
                const data = new FormData(extensionForm);
                const body = {
                    integration: Number(data.get("integration")),
                    number: String(data.get("number") || "").trim(),
                    user: data.get("user") ? Number(data.get("user")) : null,
                    label: data.get("label"),
                    active: document.getElementById("extension-active").checked,
                };
                if (editingExtension) {
                    await apiRequest(`/api/v1/telephony/extensions/${editingExtension.id}/`, {method: "PATCH", body});
                } else {
                    await apiRequest("/api/v1/telephony/extensions/", {method: "POST", body});
                }
                extensionDialog.close();
                globalMessage("داخلی ذخیره شد.", true);
                await loadExtensions();
            });
        });
        extensions.open = openExtension;
    }

    async function loadExtensions() {
        if (!extensions) return;
        try {
            const rows = await apiRequest("/api/v1/telephony/extensions/");
            const names = Object.fromEntries(integrations.map((integration) => [integration.id, integration.name]));
            extensions.fill(rows.map((extension) => {
                const row = document.createElement("tr");
                const number = appendCell(row, toPersianDigits(extension.number));
                number.className = "fw-semibold";
                appendCell(row, names[extension.integration] || "");
                appendCell(row, extension.user_display);
                appendCell(row, extension.label);
                const active = document.createElement("td");
                active.appendChild(toggle(extension.active, `فعال بودن داخلی ${extension.number}`, async (value) => {
                    await apiRequest(`/api/v1/telephony/extensions/${extension.id}/`, {method: "PATCH", body: {active: value}});
                    await loadExtensions();
                }));
                row.appendChild(active);
                const actions = document.createElement("td");
                actions.className = "row-actions";
                actions.append(
                    button("ویرایش", "btn-light", () => extensions.open(extension)),
                    button("حذف", "btn-light-danger", async (node) => {
                        if (!await confirmDialog(`داخلی ${toPersianDigits(extension.number)} حذف شود؟ تماس‌های گذشته‌اش سر جایشان می‌مانند.`)) return;
                        node.disabled = true;
                        try {
                            await apiRequest(`/api/v1/telephony/extensions/${extension.id}/`, {method: "DELETE"});
                            await loadExtensions();
                        } catch (error) {
                            node.disabled = false;
                            showError(error);
                        }
                    }),
                );
                row.appendChild(actions);
                return row;
            }));
        } catch (error) {
            extensions.loading.hidden = true;
            showError(error);
        }
    }

    loadConnections().then(() => {
        loadLogs(1);
        loadExtensions();
        // Arrived from «سرویس پست» → «ساختن/ویرایش اتصال»: open that
        // connection's editor, or a new one for its provider.
        const wanted = new URLSearchParams(window.location.search).get("edit");
        if (wanted === POST_PROVIDER && providersByKey[POST_PROVIDER]) {
            const existing = integrations.find((integration) => integration.provider_key === POST_PROVIDER);
            openConnection(existing || null, POST_PROVIDER);
        }
    });
    loadSubscriptions();
    loadTokens();
}

/**
 * The «آزمایش اتصال» buttons of the built-in rows, wherever they are drawn
 * (this page, and «سرویس پست»'s own page). Each posts to the URL its row
 * declared and prints what came back — the provider's own words.
 */
export function bindIntegrationTests(root = document) {
    root.querySelectorAll("[data-integration-test]").forEach((button) => {
        const card = button.closest("[data-integration], #post-connection");
        const result = card?.querySelector("[data-integration-result]");
        button.addEventListener("click", async () => {
            button.disabled = true;
            if (result) {
                result.hidden = false;
                result.className = "alert alert-light fs-8 mt-3 mb-0";
                result.textContent = "در حال آزمودن اتصال…";
            }
            try {
                const data = await apiRequest(button.dataset.integrationTest, {
                    method: "POST",
                    body: {},
                });
                // Two answer shapes: a built-in service's own test
                // (`success`, `status_detail`) and a framework connection's
                // (`ok`, `message`).
                const ok = data.success ?? data.ok;
                if (result) {
                    result.className = `alert fs-8 mt-3 mb-0 ${ok ? "alert-success" : "alert-danger"}`;
                    // The provider's own words, not a sentence written
                    // here: an operator debugging a gateway needs what
                    // the gateway actually said.
                    result.textContent = data.status_detail || data.message || (ok ? "اتصال برقرار است." : "اتصال برقرار نشد.");
                }
            } catch (error) {
                if (result) result.hidden = true;
                showError(error);
            } finally {
                button.disabled = false;
            }
        });
    });
}

export function setupIntegrations() {
    bindIntegrationTests();
    setupIntegrationFramework();
}
