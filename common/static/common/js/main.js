import {PAGES} from "dolphin/pages.js";
import {setupAttachmentsPanel} from "dolphin/ui/attachments.js";
import {setupBusyButtons} from "dolphin/shell/busy.js";
import {setupCallPopup, setupClickToCall} from "dolphin/shell/telephony.js";
import {setupChartThemeRedraw, setupNav, setupNavActiveState, setupPageTabs, setupSidebarAccordionScroll, setupSidebarPeekGuard, setupThemeModePopup, setupUserMenu} from "dolphin/shell/nav.js";
import {setupChat, setupChatUnreadPoll} from "dolphin/shell/chat.js";
import {setupDecimalInputs} from "dolphin/core/decimal.js";
import {setupDialogBackdropClose} from "dolphin/ui/dialogs.js";
import {setupSegmentedControls} from "dolphin/ui/segmented.js";
import {setupGlobalSearch} from "dolphin/shell/search.js";
import {setupGoToAccounting} from "dolphin/shell/accounting-link.js";
import {setupJalaliInputs} from "dolphin/ui/jalali-picker.js";
import {setupLatinDigitInputs} from "dolphin/core/digits.js";
import {setupListCharts} from "dolphin/ui/list-charts.js";
import {setupListFilterPopovers, setupPopoverDismissal} from "dolphin/ui/popover.js";
import {setupLogout, setupSessionsDialog} from "dolphin/shell/session.js";
import {setupMoneyInputs} from "dolphin/core/money.js";
import {setupProfileDialog} from "dolphin/shell/profile-dialog.js";
import {setupRealtime} from "dolphin/shell/realtime.js";
import {setupReminderBell} from "dolphin/shell/reminders.js";
import {setupSearchableSelects} from "dolphin/ui/searchable-select.js";

function boot() {

    setupJalaliInputs();
    setupNav();
    setupBusyButtons();
    setupNavActiveState();
    setupPageTabs();
    setupSidebarAccordionScroll();
    setupLogout();
    setupUserMenu();
    setupSessionsDialog();
    setupDialogBackdropClose();

    // A denied page is served with the error card in place of its content, so
    // its module has no markup to bind to and every call it makes would be
    // refused anyway. Navigation and sign-out above still work; the module does
    // not run, which is what stopped an uncaught TypeError from being thrown
    // behind the Persian "دسترسی مجاز نیست" card.
    if (document.getElementById("app-error")) return;

    // Every price field on the page groups itself as it is typed. Bound once
    // here rather than per module, because a price is a price on whichever
    // screen it appears; dialogs are in the DOM at load, so they are covered.
    setupMoneyInputs();
    // Rates and percentages: numbers only, however they are typed or pasted.
    setupDecimalInputs();
    // Segmented toggles redraw from the hidden input they stand for.
    setupSegmentedControls();
    // Persian digits in every numeric field, including ones built later.
    setupLatinDigitInputs();

    setupSearchableSelects();
    setupRealtime();
    setupChartThemeRedraw();
    setupSidebarPeekGuard();
    setupThemeModePopup();
    setupProfileDialog();
    setupListFilterPopovers();

    // Any page that declares an attachments panel gets one wired up,
    // whichever page it is — same reasoning as the chart cards below.
    setupAttachmentsPanel();

    // Any page that declares a chart card gets one, whichever page it is.
    setupListCharts();

    // The chat drawer, the reminder bell and search all live in the header
    // shell, so every page that has one wires it up — same reasoning as the
    // two lines above, not only a page named after the feature.
    setupPopoverDismissal();
    setupGlobalSearch();
    // Telephony (2.23.0): click-to-call anywhere, and the incoming-call
    // popup for someone with an extension.
    setupClickToCall();
    setupCallPopup();
    setupReminderBell();
    setupChatUnreadPoll();
    // The header drawer, on every page (2018.5's original instance,
    // unchanged); the full page, only where `/chat/`'s own markup exists —
    // `setupChat` no-ops when `chat-page-thread-list` is not on the page.
    setupChat("chat-drawer", {container: "dolphin_drawer_chat", toggle: "dolphin_drawer_chat_toggle"});
    setupChat("chat-page", {isOpen: () => true, openFromUrl: true});
    setupGoToAccounting(); // PRELIMINARY, UNCOMMITTED — see integration/apps.py

    const page = document.body.dataset.page;

    // A page's own module is fetched only when that page is opened.
    const loadPage = PAGES[page];
    if (loadPage) loadPage();
}

boot();
