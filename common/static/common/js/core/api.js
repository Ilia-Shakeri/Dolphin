export const STATUS_MESSAGES = Object.freeze({
    400: "داده‌های واردشده درست نیست. موارد مشخص‌شده را اصلاح کنید.",
    403: "اجازه انجام این کار را ندارید.",
    404: "مورد درخواستی پیدا نشد.",
    409: "این تغییر با وضعیت فعلی سامانه سازگار نیست.",
    429: "درخواست‌ها بیش از حد مجاز است. کمی بعد دوباره تلاش کنید.",
});

export class ApiError extends Error {
    constructor(status, payload) {
        super(STATUS_MESSAGES[status] || "خطایی رخ داد. دوباره تلاش کنید.");
        this.status = status;
        this.payload = payload || {};
    }
}

function csrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
}

export async function apiRequest(url, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = {Accept: "application/json", ...(options.headers || {})};
    if (!(["GET", "HEAD", "OPTIONS"].includes(method))) {
        headers["X-CSRFToken"] = csrfToken();
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
