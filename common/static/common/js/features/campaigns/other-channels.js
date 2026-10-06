/**
 * «سایر» among a campaign's ways of reaching people (2.40.22).
 *
 * Ticking «سایر» opens a field for what it is — one or several, separated by
 * «،» or a comma; unticking folds it away and nothing of it is sent. The
 * server requires it while «سایر» is ticked (`clean_other_channels`), and
 * shows the written names in place of the word «سایر».
 */
export function setupOtherChannels(form) {
    const otherBox = form.querySelector('input[name="channels"][value="other"]');
    const wrap = form.querySelector("[data-other-channels]");
    const input = wrap?.querySelector('input[name="other_channels"]');
    if (!otherBox || !wrap || !input) return {values: () => [], fill() {}};

    const sync = () => {
        wrap.hidden = !otherBox.checked;
        input.required = otherBox.checked;
        input.disabled = !otherBox.checked;
    };
    otherBox.addEventListener("change", () => {
        sync();
        if (otherBox.checked) input.focus();
    });
    form.addEventListener("reset", () => setTimeout(sync));
    sync();

    return {
        /** What is sent: the written names, or nothing when «سایر» is off. */
        values: () => (otherBox.checked
            ? input.value.split(/[،,]/).map((item) => item.trim()).filter(Boolean)
            : []),
        /** Fill from a saved campaign (the edit dialog). */
        fill(list) {
            input.value = (list || []).join("، ");
            sync();
        },
    };
}
