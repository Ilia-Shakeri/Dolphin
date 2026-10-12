/**
 * The large title that moves into the header (2.40.38).
 *
 * A page opens with its title large above the content; once the reader has
 * scrolled it under the header, the same title appears small in the header's
 * middle, so the page still says what it is — the platform's large-title
 * pattern. Text only, copied from the page heading; hidden from assistive
 * technology, which already has the heading itself.
 */
export function setupHeaderTitle() {
    const heading = document.querySelector("#dolphin_app_toolbar .page-heading");
    const container = document.querySelector("#dolphin_app_header .app-container");
    if (!heading || !container || typeof IntersectionObserver !== "function") return;
    const title = document.createElement("div");
    title.className = "header-compact-title";
    title.setAttribute("aria-hidden", "true");
    title.textContent = heading.textContent.trim();
    container.append(title);
    const header = document.getElementById("dolphin_app_header");
    new IntersectionObserver(([entry]) => {
        document.body.classList.toggle("is-title-collapsed", !entry.isIntersecting && entry.boundingClientRect.top < 0 + (header?.offsetHeight || 0));
    }, {rootMargin: `-${header?.offsetHeight || 60}px 0px 0px 0px`}).observe(heading);
}
