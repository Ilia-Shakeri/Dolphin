import {apiRequest} from "dolphin/core/api.js";
import {globalMessage, showError} from "dolphin/core/messages.js";
import {setupProfile} from "dolphin/shell/session.js";

// Any searchable select present in the served markup. A page that fills its
// options later calls this again for its own block; binding twice is a
// no-op, so neither has to know about the other.

/**
 * The theme row in the user menu, and the small popup beside it.
 *
 * `DolphinThemeMode` already binds the three buttons and does the switching; it
 * finds them by `data-dolphin-element` wherever they sit, so all that is left is
 * showing and hiding the popup and keeping the row's own label current.
 *
 * Opened on hover and on click. Hover alone would strand a touch screen,
 * where there is no hover at all, and a keyboard user who tabs to the row.
 */
/**
 * The collapsed mark expands the sidebar.
 *
 * It defers to the real toggle rather than flipping the attribute itself,
 * so `DolphinToggle` stays the only thing that owns the state and writes the
 * cookie the server reads back. Two controls, one source of truth.
 */
/**
 * The profile dialog, opened from the account menu on any page.
 *
 * Loaded on first open rather than on page load: it lives in the shell now,
 * so eagerly fetching it would add a request to every single screen for a
 * form most visits never touch. Loaded once and kept, because reopening it
 * to re-read what the reader just saved would be worse than stale.
 */
/* --- the profile picture ------------------------------------------------

   Product owner, 2026-09-20: «آپلود عکس پروفایل برای بازاریاب‌ها مثل پنل
   قالب مرجع، با برش/تغییر اندازه و محدودیت حجم و فرمت؛ به‌صورت پیش‌فرض از
   آواتارهای کارتونی پیش‌فرض استفاده شود».

   The crop and the resize happen here, in a canvas, before anything is
   sent: a photo straight off a phone is three or four megabytes and the
   wrong shape, and uploading it to be rejected is a worse experience than
   fixing it first. The server re-checks the size and sniffs the real type
   regardless — a client is a convenience, never the boundary.
*/

//: What a stored avatar is normalised to. Square, because every place it
//: is shown is a circle, and 512 because that is sharp on a retina screen
//: at the largest size the panel draws it (the profile dialog's 100px
//: frame) and still well under a hundred kilobytes as JPEG.
const AVATAR_EDGE = 512;
//: Quality chosen against the size ceiling rather than by eye: 0.85 keeps
//: a 512² photograph comfortably inside a few hundred kilobytes.
const AVATAR_QUALITY = 0.85;

/**
 * A picked file as a square, downscaled JPEG blob.
 *
 * Centre-cropped to the shorter edge — the crop a round frame implies,
 * and the one every avatar picker does without asking. A picture already
 * square and already small still goes through this, because re-encoding
 * once is cheaper than deciding whether it needs to.
 */
async function cropAvatarFile(file) {
    const source = await new Promise((resolve, reject) => {
        const image = new Image();
        const url = URL.createObjectURL(file);
        image.onload = () => { URL.revokeObjectURL(url); resolve(image); };
        image.onerror = () => { URL.revokeObjectURL(url); reject(new Error("decode")); };
        image.src = url;
    });
    const edge = Math.min(source.naturalWidth, source.naturalHeight);
    if (!edge) throw new Error("empty");
    const canvas = document.createElement("canvas");
    canvas.width = AVATAR_EDGE;
    canvas.height = AVATAR_EDGE;
    const context = canvas.getContext("2d");
    context.drawImage(
        source,
        (source.naturalWidth - edge) / 2,
        (source.naturalHeight - edge) / 2,
        edge,
        edge,
        0,
        0,
        AVATAR_EDGE,
        AVATAR_EDGE,
    );
    return new Promise((resolve, reject) => {
        canvas.toBlob(
            (blob) => (blob ? resolve(blob) : reject(new Error("encode"))),
            "image/jpeg",
            AVATAR_QUALITY,
        );
    });
}

/**
 * The picture control: a small preview outside a dialog, and the actual
 * picking — a gallery of default cartoons plus the upload — inside it.
 *
 * Product owner, 2026-09-21: «کاربران باید بتوانند بین عکس‌های پیش‌فرض
 * انتخاب کنند و اپشن آپلود شخصی هم در مودالی که تازه باز می‌شود باشد».
 * Split across two containers rather than one `root` (the shape this had
 * before the gallery existed) because the preview circle and the dialog
 * that changes it are no longer the same box.
 *
 * `endpoint` is the account owner's own by default; the user-admin page
 * would pass another person's. Which of those the reader may actually
 * change is the server's decision (`accounts.avatars._require_may_edit`),
 * not something hidden here. `endpoint` doubles as the base for the
 * default-choice endpoint (`${endpoint}default/`) — both routes are
 * registered in pairs for exactly this reason (`accounts/urls.py`).
 */
function setupAvatarInput({previewRoot, dialog, endpoint}) {
    if (!previewRoot || !dialog) return null;
    const image = previewRoot.querySelector(".avatar-input-image");
    const picker = dialog.querySelector('input[type="file"]');
    const clear = dialog.querySelector("[id$='-clear']");
    const errorNote = dialog.querySelector("[id$='-error']");
    const grid = dialog.querySelector(".avatar-picker-grid");
    const gridLoading = dialog.querySelector("#avatar-picker-loading");
    const chooseEndpoint = `${endpoint}default/`;

    let current = null; // the last state the server reported
    let tiles = null; // built once the gallery is first opened

    function fail(message) {
        if (!errorNote) return;
        errorNote.textContent = message;
        errorNote.hidden = false;
    }

    function paintSelection() {
        if (!tiles) return;
        const activeName = !current?.has_avatar ? current?.chosen_default_name : "";
        tiles.forEach((tile) => {
            const active = Boolean(activeName) && tile.dataset.name === activeName;
            tile.classList.toggle("is-selected", active);
            tile.setAttribute("aria-selected", active ? "true" : "false");
        });
    }

    function show(state) {
        current = state;
        // `?v=` because the URL does not change when the picture does —
        // the same cache-bust the brand logo uses.
        image.src = state.url ? `${state.url}?v=${Date.now()}` : "";
        image.hidden = !state.url;
        if (clear) clear.hidden = !state.has_avatar;
        if (errorNote) errorNote.hidden = true;
        previewRoot.hidden = false;
        paintSelection();
    }

    async function load() {
        try {
            show(await apiRequest(endpoint));
        } catch (error) {
            showError(error);
        }
    }

    async function chooseDefault(name, tile) {
        if (tile.disabled) return;
        tile.disabled = true;
        try {
            show(await apiRequest(chooseEndpoint, {method: "POST", body: {name}}));
            globalMessage("تصویر پروفایل ذخیره شد.", true);
        } catch (error) {
            showError(error);
        } finally {
            tile.disabled = false;
        }
    }

    // Fetched once and cached: the gallery is the same 52 cartoons for
    // everyone and does not change while the dialog is open, so a second
    // visit re-lists elements already in the DOM rather than re-fetching.
    async function loadGrid() {
        if (tiles || !grid) return;
        try {
            const defaults = await apiRequest("/api/v1/avatar-defaults/");
            tiles = defaults.map((item) => {
                const tile = document.createElement("button");
                tile.type = "button";
                tile.className = "avatar-picker-tile";
                tile.dataset.name = item.name;
                tile.setAttribute("role", "option");
                tile.setAttribute("aria-selected", "false");
                tile.title = "انتخاب این آواتار";
                const img = document.createElement("img");
                img.src = item.url;
                img.alt = "";
                img.loading = "lazy";
                tile.append(img);
                tile.addEventListener("click", () => chooseDefault(item.name, tile));
                return tile;
            });
            grid.replaceChildren(...tiles);
            if (gridLoading) gridLoading.hidden = true;
            grid.hidden = false;
            paintSelection();
        } catch (error) {
            showError(error);
        }
    }

    picker?.addEventListener("change", async () => {
        const file = picker.files && picker.files[0];
        if (!file) return;
        if (errorNote) errorNote.hidden = true;
        let blob;
        try {
            blob = await cropAvatarFile(file);
        } catch (error) {
            // A file the browser itself cannot decode is not worth
            // sending: the server would only reject it, more slowly.
            fail("این فایل یک تصویر خوانا نیست.");
            picker.value = "";
            return;
        }
        const body = new FormData();
        body.append("avatar", blob, "avatar.jpg");
        try {
            // `raw` so `apiRequest` leaves the multipart boundary the
            // FormData carries rather than stamping a JSON content type
            // over it.
            show(await apiRequest(endpoint, {method: "POST", body, raw: true}));
            globalMessage("تصویر پروفایل ذخیره شد.", true);
        } catch (error) {
            showError(error);
        } finally {
            // So picking the same file twice in a row still fires.
            picker.value = "";
        }
    });

    clear?.addEventListener("click", async () => {
        try {
            show(await apiRequest(endpoint, {method: "DELETE"}));
            globalMessage("تصویر پروفایل حذف شد؛ آواتار پیش‌فرض بازگشت.", true);
        } catch (error) {
            showError(error);
        }
    });

    load();
    return {load, loadGrid};
}

export function setupProfileDialog() {
    const dialog = document.getElementById("profile-dialog");
    const open = document.getElementById("open-profile");
    if (!dialog || !open) return;
    let loaded = false;
    let avatarInput = null;

    const avatarDialog = document.getElementById("avatar-picker-dialog");
    const openAvatarPicker = document.getElementById("open-avatar-picker");
    openAvatarPicker?.addEventListener("click", () => {
        if (!avatarDialog) return;
        avatarDialog.showModal();
        avatarInput?.loadGrid();
    });
    avatarDialog?.querySelectorAll("[data-close-dialog]").forEach((button) =>
        button.addEventListener("click", () => avatarDialog.close()),
    );

    open.addEventListener("click", async () => {
        dialog.showModal();
        if (loaded) return;
        loaded = true;
        try {
            await setupProfile();
            avatarInput = setupAvatarInput({
                previewRoot: document.getElementById("profile-avatar"),
                dialog: avatarDialog,
                endpoint: "/api/v1/profile/avatar/",
            });
        } catch (error) {
            // `setupProfile` reports its own failure into the dialog; this
            // only stops one bad load from wedging the button shut.
            loaded = false;
            showError(error);
        }
    });
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) =>
        button.addEventListener("click", () => dialog.close()),
    );
}
