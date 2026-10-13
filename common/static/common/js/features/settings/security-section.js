import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate} from "dolphin/core/jalali.js";
import {clearMessages, globalMessage, withSubmit} from "dolphin/core/messages.js";
import {guardDirtyDialog} from "dolphin/ui/dialogs.js";

const STATUS = "/api/v1/auth/me/two-factor/";

/** `ABCD EFGH …`: a long key in groups a person can copy by eye. */
function grouped(secret) {
    return secret.replace(/(.{4})/g, "$1 ").trim();
}

/**
 * «امنیت» → ورود دومرحله‌ای (2.40.42): the reader's own authenticator.
 *
 * Turning it on is three panes in one dialog — the password, then the QR code
 * (or the key typed by hand) and the first code that proves the app works,
 * then the recovery codes, shown once. Turning it off and new recovery codes
 * both ask for the password and a current code. The server decides every
 * step (`accounts/two_factor_views.py`); this only asks and shows.
 */
export function setupSecuritySection() {
    const card = document.getElementById("two-factor-card");
    if (!card) return;
    const loading = document.getElementById("two-factor-loading");
    const state = document.getElementById("two-factor-state");
    const badge = document.getElementById("two-factor-badge");
    const summary = document.getElementById("two-factor-summary");
    const enable = document.getElementById("two-factor-enable");
    const codesButton = document.getElementById("two-factor-codes");
    const disable = document.getElementById("two-factor-disable");
    const unavailable = document.getElementById("two-factor-unavailable");

    function draw(status) {
        loading.hidden = true;
        state.hidden = false;
        badge.className = `badge fs-7 ${status.enabled ? "badge-light-success" : "badge-light"}`;
        badge.textContent = status.enabled ? "روشن" : "خاموش";
        summary.textContent = status.enabled
            ? `از ${displayDate(status.enabled_at)} — ${toPersianDigits(String(status.recovery_codes_left))} کد بازیابی باقی مانده`
            : "ورود فقط با نام کاربری و گذرواژه است.";
        enable.hidden = status.enabled || !status.available;
        codesButton.hidden = !status.enabled;
        disable.hidden = !status.enabled;
        unavailable.hidden = status.enabled || status.available;
    }

    async function refresh() {
        try {
            draw(await apiRequest(STATUS));
        } catch (error) {
            loading.textContent = "وضعیت دریافت نشد؛ صفحه را دوباره باز کنید.";
        }
    }

    // --- turning it on ------------------------------------------------------
    const dialog = document.getElementById("two-factor-dialog");
    const startForm = document.getElementById("two-factor-start-form");
    const confirmForm = document.getElementById("two-factor-confirm-form");
    const panes = [...dialog.querySelectorAll("[data-two-factor-pane]")];
    const codesList = document.getElementById("two-factor-codes-list");
    let shownCodes = [];
    guardDirtyDialog(dialog, startForm);
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    dialog.addEventListener("close", refresh);

    function showPane(name) {
        panes.forEach((pane) => { pane.hidden = pane.dataset.twoFactorPane !== name; });
        dialog.querySelector(`[data-two-factor-pane="${name}"] input`)?.focus();
    }

    function showCodes(codes, title) {
        shownCodes = codes;
        codesList.replaceChildren(...codes.map((code) => {
            const item = document.createElement("li");
            item.textContent = code;
            return item;
        }));
        document.getElementById("two-factor-dialog-title").textContent = title;
        showPane("codes");
        if (!dialog.open) dialog.showModal();
    }

    enable.addEventListener("click", () => {
        startForm.reset();
        confirmForm.reset();
        clearMessages(startForm);
        clearMessages(confirmForm);
        document.getElementById("two-factor-dialog-title").textContent = "روشن کردن ورود دومرحله‌ای";
        showPane("password");
        dialog.showModal();
    });

    startForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(startForm, async () => {
            const enrolment = await apiRequest("/api/v1/auth/me/two-factor/setup/", {
                method: "POST", body: {password: startForm.elements.password.value},
            });
            document.getElementById("two-factor-qr").src = enrolment.qr;
            document.getElementById("two-factor-secret").textContent = grouped(enrolment.secret);
            document.getElementById("two-factor-open-app").href = enrolment.otpauth_uri;
            startForm.reset();
            showPane("scan");
        });
    });

    confirmForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(confirmForm, async () => {
            const result = await apiRequest("/api/v1/auth/me/two-factor/confirm/", {
                method: "POST", body: {code: confirmForm.elements.code.value},
            });
            globalMessage("ورود دومرحله‌ای روشن شد.", true);
            showCodes(result.recovery_codes, "کدهای بازیابی");
        });
    });

    document.getElementById("two-factor-codes-copy").addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(shownCodes.join("\n"));
            globalMessage("کدها کپی شد.", true);
        } catch (error) {
            globalMessage("کپی ممکن نشد؛ کدها را از روی صفحه بنویسید.");
        }
    });
    document.getElementById("two-factor-codes-download").addEventListener("click", () => {
        const text = `Dolphin — recovery codes\n\n${shownCodes.join("\n")}\n`;
        const link = document.createElement("a");
        link.href = URL.createObjectURL(new Blob([text], {type: "text/plain;charset=utf-8"}));
        link.download = "dolphin-recovery-codes.txt";
        link.click();
        setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    });
    document.getElementById("two-factor-done").addEventListener("click", () => dialog.close());

    // --- turning it off, and new recovery codes -------------------------------
    const check = document.getElementById("two-factor-check-dialog");
    const checkForm = document.getElementById("two-factor-check-form");
    let checkAction = null;
    guardDirtyDialog(check, checkForm);
    check.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => check.close()));

    function askCheck({title, text, submitLabel, danger, action}) {
        checkForm.reset();
        clearMessages(checkForm);
        document.getElementById("two-factor-check-title").textContent = title;
        document.getElementById("two-factor-check-text").textContent = text;
        const submit = document.getElementById("two-factor-check-submit");
        submit.textContent = submitLabel;
        submit.className = `btn ${danger ? "btn-danger" : "btn-primary"}`;
        checkAction = action;
        check.showModal();
        checkForm.elements.password.focus();
    }

    checkForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(checkForm, async () => {
            const body = {password: checkForm.elements.password.value, code: checkForm.elements.code.value};
            await checkAction(body);
        });
    });

    disable.addEventListener("click", () => askCheck({
        title: "خاموش کردن ورود دومرحله‌ای",
        text: "از این پس ورود فقط با گذرواژه است. گذرواژه و کد برنامه (یا یک کد بازیابی) را وارد کنید.",
        submitLabel: "خاموش کردن",
        danger: true,
        action: async (body) => {
            draw(await apiRequest("/api/v1/auth/me/two-factor/disable/", {method: "POST", body}));
            check.close();
            globalMessage("ورود دومرحله‌ای خاموش شد.", true);
        },
    }));

    codesButton.addEventListener("click", () => askCheck({
        title: "کدهای بازیابی تازه",
        text: "ده کد تازه ساخته می‌شود و کدهای قبلی دیگر کار نمی‌کنند. گذرواژه و کد برنامه را وارد کنید.",
        submitLabel: "ساختن کدهای تازه",
        danger: false,
        action: async (body) => {
            const result = await apiRequest("/api/v1/auth/me/two-factor/recovery-codes/", {method: "POST", body});
            check.close();
            showCodes(result.recovery_codes, "کدهای بازیابی تازه");
        },
    }));

    refresh();
}
