/**
 * A segmented toggle: a few mutually exclusive options shown side by side.
 *
 * Markup: a `.dolphin-segmented[role=radiogroup][data-segmented-for=<id>]` holding
 * `button[role=radio][data-value]` options, and an `<input type="hidden">` with
 * that id, which is what the form submits and what other code reads or listens
 * to. Clicking an option writes the hidden input and fires its `change` event;
 * changing the hidden input from code (or resetting the form) redraws the
 * toggle, so the two can never disagree.
 */
export function syncSegmented(group) {
    const input = document.getElementById(group.dataset.segmentedFor);
    if (!input) return;
    group.querySelectorAll('[role="radio"]').forEach((option) => {
        const selected = option.dataset.value === input.value;
        option.classList.toggle("is-selected", selected);
        option.setAttribute("aria-checked", String(selected));
        option.tabIndex = selected ? 0 : -1;
    });
}

export function setupSegmentedControls(root = document) {
    root.querySelectorAll(".dolphin-segmented[data-segmented-for]").forEach((group) => {
        if (group.dataset.segmentedBound) return;
        group.dataset.segmentedBound = "1";
        const input = document.getElementById(group.dataset.segmentedFor);
        if (!input) return;
        const choose = (option) => {
            if (input.value === option.dataset.value) return;
            input.value = option.dataset.value;
            input.dispatchEvent(new Event("change", {bubbles: true}));
        };
        group.addEventListener("click", (event) => {
            const option = event.target.closest('[role="radio"]');
            if (option && !option.disabled) choose(option);
        });
        group.addEventListener("keydown", (event) => {
            if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
            const options = [...group.querySelectorAll('[role="radio"]:not(:disabled)')];
            const index = options.findIndex((option) => option.dataset.value === input.value);
            const step = ["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1;
            const next = options[(index + step + options.length) % options.length];
            if (next) {
                event.preventDefault();
                choose(next);
                next.focus();
            }
        });
        input.addEventListener("change", () => syncSegmented(group));
        input.form?.addEventListener("reset", () => setTimeout(() => syncSegmented(group), 0));
        syncSegmented(group);
    });
}
