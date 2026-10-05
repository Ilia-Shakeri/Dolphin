import {bindIntegrationTests} from "dolphin/features/settings/integrations.js";

/**
 * «سرویس پست» (2.40.7): the page is the connection's status, its details and
 * the guide, all rendered by the server; the one control that needs script
 * is «آزمایش اتصال», the same button the integrations page draws.
 */
export function setupPostProviderSettings() {
    bindIntegrationTests(document.getElementById("post-connection") || document);
}
