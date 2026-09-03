"""Persian names for the operations the activity log records.

«رویداد های سامانه باید فارسی باشند چون سایت و پنل فارسی است.» — the panel is
Persian, so what it shows a reader must be Persian too.

**The stored value does not change.** `ActivityLog.operation` keeps its
`noun.verb` ASCII form, because it is a machine contract: the log is filtered by
it, the API exposes it, and rows already written carry it. Translating at write
time would have made every historical row unsearchable by the name the new rows
use, and would have put display text inside an audit record — the one table that
should be hardest to rewrite.

So this maps the stored value to what a reader sees, and nothing else. An
operation with no entry here falls back to its stored form: a missing
translation shows an ugly label, never a blank one, and never hides that the
event happened.
"""

#: Stored operation -> what the panel shows. Grouped by the object the
#: operation acts on, in the order the operations appear in the product.
OPERATION_LABELS = {
    # --- مشتریان -----------------------------------------------------------
    "customer.created": "ثبت مشتری",
    "customer.updated": "ویرایش مشتری",
    "customer.reactivated": "فعال‌سازی مجدد مشتری",
    "customer_phone.created": "افزودن شماره تماس",
    "customer_phone.updated": "ویرایش شماره تماس",
    "customer_phone.deactivated": "غیرفعال‌سازی شماره تماس",
    "customer_ledger.appended": "ثبت حرکت در دفتر حساب",
    # --- سرنخ و جامعه هدف ---------------------------------------------------
    "lead.created": "ثبت سرنخ",
    "lead.updated": "ویرایش سرنخ",
    "lead.reassigned": "واگذاری سرنخ",
    "target_audience.added": "افزودن به جامعه هدف",
    "target_audience.updated": "ویرایش جامعه هدف",
    "target_audience.status_derived": "به‌روزرسانی خودکار وضعیت جامعه هدف",
    # --- کالا و انبار -------------------------------------------------------
    "product.created": "ثبت کالا",
    "product.updated": "ویرایش کالا",
    "product.deactivated": "غیرفعال‌سازی کالا",
    "product.reactivated": "فعال‌سازی مجدد کالا",
    "product_category.created": "ثبت دسته‌بندی کالا",
    "product_category.updated": "ویرایش دسته‌بندی کالا",
    "product_category.deactivated": "غیرفعال‌سازی دسته‌بندی کالا",
    "product_category.reactivated": "فعال‌سازی مجدد دسته‌بندی کالا",
    "warehouse.created": "ثبت انبار",
    "warehouse.updated": "ویرایش انبار",
    "warehouse.deactivated": "غیرفعال‌سازی انبار",
    "warehouse.reactivated": "فعال‌سازی مجدد انبار",
    "stock_movement.recorded": "ثبت حرکت موجودی",
    # --- اسناد فروش ---------------------------------------------------------
    "quotation.created": "ثبت پیش‌فاکتور",
    "quotation.updated": "ویرایش پیش‌فاکتور",
    "quotation.items_replaced": "تغییر اقلام پیش‌فاکتور",
    "quotation.status_changed": "تغییر وضعیت پیش‌فاکتور",
    "order.created": "ثبت سفارش",
    "order.updated": "ویرایش سفارش",
    "order.items_replaced": "تغییر اقلام سفارش",
    "order.status_changed": "تغییر وضعیت سفارش",
    "order.cancelled_for_shortage": "لغو سفارش به دلیل کمبود موجودی",
    "sale.created": "ثبت فروش",
    "sale.cancelled": "ابطال فروش",
    # --- فاکتور -------------------------------------------------------------
    "invoice.created": "ثبت فاکتور",
    "invoice.updated": "ویرایش فاکتور",
    "invoice.items_replaced": "تغییر اقلام فاکتور",
    "invoice.issued": "صدور فاکتور",
    "invoice.cancelled": "ابطال فاکتور",
    "invoice.reissued": "ابطال و صدور مجدد فاکتور",
    "invoice.order_linked": "پیوند فاکتور به سفارش",
    "invoice.manual_paid_entry": "ثبت دستی مبلغ پرداختی",
    # --- دریافت و پرداخت ----------------------------------------------------
    "payment.registered": "ثبت سند مالی",
    "payment.allocated": "تخصیص دریافت به فاکتور",
    "payment.allocation_released": "آزادسازی تخصیص",
    "payment.cancelled": "ابطال سند مالی",
    "payment.corrected": "اصلاح سند مالی",
    "cheque.status_changed": "تغییر وضعیت چک",
    "cheque.registration_changed": "تغییر حالت ثبت چک",
    "installment_plan.created": "ثبت طرح اقساط",
    "installment_plan.cancelled": "لغو طرح اقساط",
    # --- خدمات پس از فروش ---------------------------------------------------
    "after_sales.created": "ثبت درخواست پس از فروش",
    "after_sales.assigned": "واگذاری درخواست پس از فروش",
    "after_sales.status_changed": "تغییر وضعیت درخواست پس از فروش",
    "after_sales.closed": "بستن درخواست پس از فروش",
    # --- مدارک و پیامک ------------------------------------------------------
    "sales_document.registered": "ثبت مدرک فروش",
    "sales_document.postal_status_changed": "تغییر وضعیت پستی مدرک",
    "sales_document.deactivated": "غیرفعال‌سازی مدرک فروش",
    "inbound_sms.stored": "دریافت پیامک",
    "outbound_sms.sent": "ارسال پیامک",
    "outbound_sms.failed": "ارسال ناموفق پیامک",
    "attachment.uploaded": "افزودن پیوست",
    "attachment.deleted": "حذف پیوست",
    # --- کاربران ------------------------------------------------------------
    "user.created": "ثبت کاربر",
    "user.updated": "ویرایش کاربر",
    "user.profile_updated": "ویرایش پروفایل",
    "user.role_changed": "تغییر نقش کاربر",
    "user.permissions_overridden": "تغییر مجوزهای اختصاصی کاربر",
    "user.permissions_reset": "بازنشانی مجوزهای کاربر به پیش‌فرض نقش",
    "user.sessions_revoked": "ابطال نشست‌های کاربر",
    "user.platform_admin_bootstrapped": "ایجاد مدیر پلتفرم",
    "user.uat_seeded": "ایجاد داده آزمایشی",
    # --- عمومی --------------------------------------------------------------
    "cancel": "ابطال",
}


def operation_label(operation):
    """The Persian name for a stored operation, or the stored value itself.

    Falling back to the raw value is deliberate. A new operation added without a
    translation should look unfinished in the panel; it must never disappear
    from the audit trail, and it must never be shown as blank — an audit row a
    reader cannot name is worse than one named in English.
    """
    if not operation:
        return "—"
    return OPERATION_LABELS.get(operation, operation)
