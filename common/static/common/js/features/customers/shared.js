import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDay, pad2, tehranParts} from "dolphin/core/jalali.js";

/**
 * A chart bucket's own axis label, at the width the server bucketed it to.
 *
 * `displayDay` on an hourly bucket prints the same calendar day
 * twenty-four times in a row, which reads as twenty-four identical
 * points. The full «۱۴۰۵/۰۶/۲۸ ۱۹:۰۰» is the other extreme — measured
 * on a live hourly chart, Apex trimmed it to «۱۴۰۵/۰۶/۲۸ ۱۹…» and the
 * hour, the one part that differs between neighbours, was the part cut
 * off. An hourly window is at most two days long and its title already
 * names it, so the hour alone is what the axis carries.
 */
export function bucketLabel(bucket, granularity) {
    if (granularity !== "hour") return displayDay(bucket);
    const parts = tehranParts(bucket);
    return parts ? toPersianDigits(`${pad2(parts.hour)}:00`) : displayDay(bucket);
}
