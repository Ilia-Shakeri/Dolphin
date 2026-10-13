import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate, displayDay} from "dolphin/core/jalali.js";
import {appendCell} from "dolphin/ui/table.js";

/**
 * The header's stat cards #4–#7 (2.20.0). The server rendered a shell
 * only for the cards this reader may see; this fills their values for
 * the chosen period and re-fills them when the period changes.
 */
export function setupProfileCards(personType, personId) {
    const host = document.querySelector("[data-profile-cards]");
    if (!host) return;
    const select = document.getElementById("profile-card-period");

    function paint(box, card) {
        const value = box.querySelector("[data-card-value]");
        value.textContent = card.value;
        value.classList.toggle("text-danger", card.accent === "danger");
        box.title = card.tooltip || "";
        const icon = box.querySelector("[data-card-icon]");
        icon.classList.remove("text-gray-500", "text-success", "text-primary", "text-warning", "text-danger");
        icon.classList.add(card.accent ? `text-${card.accent}` : "text-gray-500");
        const trend = box.querySelector("[data-card-trend]");
        if (card.trend && card.trend.direction !== "flat") {
            const up = card.trend.direction === "up";
            trend.className = `badge fs-8 ms-2 ${up ? "badge-light-success" : "badge-light-danger"}`;
            trend.textContent = `${up ? "↑" : "↓"} ${card.trend.display}`;
            trend.title = card.trend.tooltip || "";
            trend.hidden = false;
        } else {
            trend.hidden = true;
        }
    }

    function readCards() {
        const query = new URLSearchParams({period: select ? select.value : ""});
        return apiRequest(`/api/v1/profiles/${personType}/${personId}/cards/?${query}`);
    }

    function paintCards(data) {
        data.cards.forEach((card) => {
            const box = host.querySelector(`[data-profile-card="${card.key}"]`);
            if (box) paint(box, card);
        });
    }

    async function load() {
        host.setAttribute("aria-busy", "true");
        host.querySelectorAll("[data-card-value]").forEach((node) => { node.textContent = "…"; });
        try {
            paintCards(await readCards());
        } catch (error) {
            host.querySelectorAll("[data-profile-card]").forEach((box) => {
                box.querySelector("[data-card-value]").textContent = "—";
                box.title = "دریافت این رقم ممکن نشد.";
            });
        } finally {
            host.removeAttribute("aria-busy");
        }
    }

    select?.addEventListener("change", load);
    const scoreCard = host.querySelector("[data-score-card]");
    if (scoreCard) {
        const open = () => openScoreDialog(personType, personId);
        scoreCard.addEventListener("click", open);
        scoreCard.addEventListener("keydown", (event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            event.preventDefault();
            open();
        });
    }
    load();
    return {readCards, paintCards};
}

/** Why the score is what it is: each factor, its points and its reason. */
async function openScoreDialog(personType, personId) {
    const dialog = document.getElementById("profile-score-dialog");
    if (!dialog) return;
    const part = (name) => dialog.querySelector(`[data-score-${name}]`);
    part("loading").hidden = false;
    part("error").hidden = true;
    part("empty").hidden = true;
    part("body").hidden = true;
    if (!dialog.open) dialog.showModal();
    try {
        const data = await apiRequest(`/api/v1/profiles/${personType}/${personId}/score/`);
        part("loading").hidden = true;
        if (!data.current) { part("empty").hidden = false; return; }
        part("value").textContent = toPersianDigits(String(data.current.score));
        const level = part("level");
        level.className = `badge fs-7 badge-light-${data.current.accent}`;
        level.textContent = data.current.level_label;
        part("when").textContent = `محاسبه‌شده ${displayDate(data.current.computed_at)}`;
        part("breakdown").replaceChildren(...data.current.breakdown.map((factor) => {
            const row = document.createElement("tr");
            appendCell(row, factor.label).className = "fw-semibold";
            appendCell(
                row,
                factor.applicable && factor.weight
                    ? `${toPersianDigits(String(factor.points).replace(".", "٫"))} از ${toPersianDigits(String(factor.weight))}`
                    : "قابل سنجش نیست",
            ).classList.toggle("text-muted", !factor.applicable || !factor.weight);
            appendCell(row, factor.reason).className = "text-gray-700";
            return row;
        }));
        part("history").replaceChildren(...data.history.map((entry) => {
            const item = document.createElement("li");
            item.className = `badge badge-light-${entry.accent} fs-8`;
            item.textContent = `${displayDay(entry.computed_at)} — ${toPersianDigits(String(entry.score))}`;
            return item;
        }));
        part("body").hidden = false;
    } catch (error) {
        part("loading").hidden = true;
        part("error").hidden = false;
    }
}
