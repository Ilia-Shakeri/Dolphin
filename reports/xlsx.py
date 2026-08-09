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
