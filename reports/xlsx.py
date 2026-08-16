from io import BytesIO

from openpyxl import Workbook

from reports.services import UserPerformanceReport


XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
REPORT_HEADERS = (
    "user_id",
    "username",
    "customers_created_count",
    "sales_count",
    "sales_amount",
    "average_sale_amount",
)
FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_spreadsheet_text(value: str) -> str:
    if value and (
        value != value.lstrip(" \t\r\n")
        or value.startswith(FORMULA_PREFIXES)
    ):
        return f"'{value}"
    return value


def build_user_performance_workbook(report: UserPerformanceReport) -> bytes:
    workbook = Workbook()
    workbook.iso_dates = True
    workbook.properties.creator = "Kariz CRM"

    sheet = workbook.active
    sheet.title = "user-performance"
    sheet.freeze_panes = "A2"
    sheet.append(REPORT_HEADERS)
    for row in report.results:
        sheet.append(
            (
                row.user_id,
                safe_spreadsheet_text(row.username),
                row.customers_created_count,
                row.sales_count,
                format(row.sales_amount, ".2f"),
                format(row.average_sale_amount, ".2f"),
            )
        )
    if sheet.max_row > 1:
        for cells in sheet.iter_rows(min_row=2, min_col=5, max_col=6):
            for cell in cells:
                cell.number_format = "@"
    sheet.auto_filter.ref = sheet.dimensions

    summary = workbook.create_sheet("summary")
    summary.append(("metric", "value"))
    summary.append(("customers_created_count", report.summary.customers_created_count))
    summary.append(("sales_count", report.summary.sales_count))
    summary.append(("sales_amount", format(report.summary.sales_amount, ".2f")))
    summary.append(("average_sale_amount", format(report.summary.average_sale_amount, ".2f")))
    summary["B4"].number_format = "@"
    summary["B5"].number_format = "@"

    filters = workbook.create_sheet("filters")
    filters.append(("field", "value"))
    filters.append(("period_start", report.period_start))
    filters.append(("period_end", report.period_end))
    filters.append(("user_id", report.user_id))
    filters.append(("sales_product_id", report.sales_product_id))

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _write_money_columns(sheet, first_column, last_column):
    """Force money columns to text so a spreadsheet never re-rounds a Decimal."""
    if sheet.max_row <= 1:
        return
    for cells in sheet.iter_rows(min_row=2, min_col=first_column, max_col=last_column):
        for cell in cells:
            cell.number_format = "@"


def _new_workbook(title):
    workbook = Workbook()
    workbook.iso_dates = True
    workbook.properties.creator = "Kariz CRM"
    sheet = workbook.active
    sheet.title = title
    sheet.freeze_panes = "A2"
    return workbook, sheet


def _finish(workbook, sheet):
    sheet.auto_filter.ref = sheet.dimensions
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


RECEIVABLES_HEADERS = (
    "customer_id", "customer_name", "invoice_count", "total_outstanding",
    "not_due", "days_1_30", "days_31_60", "days_61_90", "days_over_90",
)


def build_receivables_workbook(report):
    workbook, sheet = _new_workbook("receivables")
    sheet.append(RECEIVABLES_HEADERS)
    for row in report.results:
        sheet.append((
            row.customer_id,
            safe_spreadsheet_text(row.customer_name),
            row.invoice_count,
            format(row.total_outstanding, ".2f"),
            format(row.not_due, ".2f"),
            format(row.days_1_30, ".2f"),
            format(row.days_31_60, ".2f"),
            format(row.days_61_90, ".2f"),
            format(row.days_over_90, ".2f"),
        ))
    _write_money_columns(sheet, 4, 9)

    summary = workbook.create_sheet("summary")
    summary.append(("metric", "value"))
    summary.append(("as_of", report.as_of))
    summary.append(("total_outstanding", format(report.total_outstanding, ".2f")))
    for name, value in report.buckets.items():
        summary.append((name, format(value, ".2f")))
    _write_money_columns(summary, 2, 2)
    return _finish(workbook, sheet)


PROFIT_HEADERS = (
    "invoice_id", "number", "customer_id", "customer_name", "issued_at",
    "revenue", "cost", "profit", "margin_percent",
)


def build_profit_workbook(report):
    workbook, sheet = _new_workbook("profit")
    sheet.append(PROFIT_HEADERS)
    for row in report.results:
        sheet.append((
            row.invoice_id,
            safe_spreadsheet_text(row.number),
            row.customer_id,
            safe_spreadsheet_text(row.customer_name),
            row.issued_at,
            format(row.revenue, ".2f"),
            format(row.cost, ".2f"),
            format(row.profit, ".2f"),
            format(row.margin_percent, ".2f"),
        ))
    _write_money_columns(sheet, 6, 9)

    summary = workbook.create_sheet("summary")
    summary.append(("metric", "value"))
    summary.append(("period_start", report.period_start))
    summary.append(("period_end", report.period_end))
    summary.append(("revenue", format(report.revenue, ".2f")))
    summary.append(("cost", format(report.cost, ".2f")))
    summary.append(("profit", format(report.profit, ".2f")))
    summary.append(("margin_percent", format(report.margin_percent, ".2f")))
    summary.append(("measured_invoice_count", report.measured_invoice_count))
    summary.append(("unmeasured_invoice_count", report.unmeasured_invoice_count))
    return _finish(workbook, sheet)


VALUATION_HEADERS = (
    "warehouse_id", "warehouse_name", "product_id", "product_sku", "product_name",
    "quantity", "average_cost", "stock_value",
)


def build_inventory_valuation_workbook(report):
    workbook, sheet = _new_workbook("stock-valuation")
    sheet.append(VALUATION_HEADERS)
    for row in report.results:
        sheet.append((
            row.warehouse_id,
            safe_spreadsheet_text(row.warehouse_name),
            row.product_id,
            safe_spreadsheet_text(row.product_sku),
            safe_spreadsheet_text(row.product_name),
            row.quantity,
            format(row.average_cost, ".2f"),
            format(row.stock_value, ".2f"),
        ))
    _write_money_columns(sheet, 7, 8)

    summary = workbook.create_sheet("summary")
    summary.append(("metric", "value"))
    summary.append(("as_of", report.as_of))
    summary.append(("total_quantity", report.total_quantity))
    summary.append(("total_value", format(report.total_value, ".2f")))
    return _finish(workbook, sheet)
