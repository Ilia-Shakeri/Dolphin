// Short and plain (2.40.40, product owner: «ارورهای پنل باید فارسی و ساده باشند»).
export const STATUS_MESSAGES = Object.freeze({
    400: "لطفاً موارد مشخص‌شده را درست کنید.",
    403: "اجازهٔ این کار را ندارید.",
    404: "پیدا نشد.",
    409: "این کار الان ممکن نیست.",
    429: "تعداد تلاش‌ها زیاد شد؛ کمی بعد دوباره امتحان کنید.",
});
export const GENERIC_MESSAGE = "مشکلی پیش آمد؛ دوباره امتحان کنید.";

export class ApiError extends Error {
    constructor(status, payload) {
        super(STATUS_MESSAGES[status] || GENERIC_MESSAGE);
        this.status = status;
        this.payload = payload || {};
    }
}

function csrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
}

//: When this page last changed something on the server (2.40.34) — so the
//: live update that change sets off is recognised as the page's own echo.
let lastWrite = 0;

export function lastWriteAt() {
    return lastWrite;
}

export async function apiRequest(url, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = {Accept: "application/json", ...(options.headers || {})};
    if (!(["GET", "HEAD", "OPTIONS"].includes(method))) {
        headers["X-CSRFToken"] = csrfToken();
        lastWrite = Date.now();
    }
    if (options.body !== undefined) {
        if (options.raw) {
            // A FormData body carries its own multipart boundary. Setting
            // Content-Type by hand here would omit that boundary and the
            // upload would arrive unparseable.
            delete options.raw;
        } else {
            headers["Content-Type"] = "application/json";
            options.body = JSON.stringify(options.body);
        }
    }
    const response = await fetch(url, {...options, method, headers, credentials: "same-origin"});
    let payload = null;
    if (response.status !== 204) {
        try { payload = await response.json(); } catch (_) { payload = null; }
    }
    if (!response.ok) throw new ApiError(response.status, payload);
    return payload;
}
