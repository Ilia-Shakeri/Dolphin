/**
 * Dispatch a form event on behalf of a control the reader just operated.
 *
 * A synthetic event is not `isTrusted`, so the wizard's unsaved-changes guard
 * would ignore a date picked from the calendar or an option ticked in a
 * checklist. Marking the event `userInitiated` tells the guard it is the
 * reader's change, while values the page fills in by itself (which dispatch
 * nothing) stay ignored.
 */
export function dispatchUserEvent(element, type, init = {bubbles: true}) {
    const event = new Event(type, init);
    event.userInitiated = true;
    element.dispatchEvent(event);
}
