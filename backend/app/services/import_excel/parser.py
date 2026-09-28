"""Reads the 'Raw data' sheet layout (accounts x months) into flat rows.

Resilient to reasonable changes: months are read from the sheet's own header
cells (not assumed to be a fixed column range), missing months/years are
tolerated, and unrecognized account rows are reported as warnings rather than
crashing the import or being silently dropped.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.services.import_excel.mapping import (
    KNOWN_DERIVED_LABELS,
    MAPPINGS_BY_LABEL,
    AccountMapping,
    ExcelSheetLayout,
)

MONTH_ABBR_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "mai": 5,  # the sheet uses the German/Polish spelling for May
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


@dataclass
class ParsedSnapshotRow:
    account_mapping: AccountMapping
    snapshot_date: dt.date
    value: Decimal
    cell: str


@dataclass
class ParseResult:
    rows: list[ParsedSnapshotRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _parse_month_label(text: str) -> int | None:
    match = re.match(r"[A-Za-z]+", text.strip())
    if not match:
        return None
    key = match.group(0)[:3].lower()
    return MONTH_ABBR_MAP.get(key)


def _build_column_dates(ws: Worksheet, layout: ExcelSheetLayout) -> dict[int, dt.date]:
    """Map column index -> first-of-month date, forward-filling the year."""
    column_dates: dict[int, dt.date] = {}
    current_year: int | None = None

    for col in range(1, ws.max_column + 1):
        year_cell = ws.cell(row=layout.year_row, column=col).value
        if year_cell is not None:
            try:
                current_year = int(year_cell)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass

        month_cell = ws.cell(row=layout.month_row, column=col).value
        if month_cell is None or current_year is None:
            continue
        month = _parse_month_label(str(month_cell))
        if month is None:
            continue
        column_dates[col] = dt.date(current_year, month, 1)

    return column_dates


def parse_raw_data_sheet(
    file_path: str, layout: ExcelSheetLayout | None = None
) -> ParseResult:
    layout = layout or ExcelSheetLayout()
    wb = openpyxl.load_workbook(file_path, data_only=True)
    if layout.sheet_name not in wb.sheetnames:
        result = ParseResult()
        result.warnings.append(
            f"Sheet {layout.sheet_name!r} not found. Available sheets: {wb.sheetnames}"
        )
        return result

    ws = wb[layout.sheet_name]
    result = ParseResult()
    column_dates = _build_column_dates(ws, layout)
    if not column_dates:
        result.warnings.append(
            f"Could not find any month columns in rows {layout.year_row}/{layout.month_row}."
        )
        return result

    label_col_idx = column_index_from_string(layout.label_col)
    first_data_row = max(layout.year_row, layout.month_row) + 1

    for row in range(first_data_row, ws.max_row + 1):
        label_cell = ws.cell(row=row, column=label_col_idx).value
        if label_cell is None:
            continue
        label = str(label_cell).strip()
        if not label:
            continue

        if label in KNOWN_DERIVED_LABELS:
            continue  # a computed rollup the sheet keeps for its own charts

        mapping = MAPPINGS_BY_LABEL.get(label)
        if mapping is None:
            result.warnings.append(
                f"Row {row}: unrecognized account label {label!r} — skipped. "
                "Add it to app/services/import_excel/mapping.py to import it."
            )
            continue

        for col, snapshot_date in column_dates.items():
            raw_value = ws.cell(row=row, column=col).value
            if raw_value is None or raw_value == "":
                continue  # not tracked yet for this account/month — not a zero
            try:
                value = Decimal(str(raw_value))
            except (InvalidOperation, ValueError):
                cell_ref = f"{get_column_letter(col)}{row}"
                result.warnings.append(
                    f"Cell {cell_ref} ({label}, {snapshot_date}): non-numeric value "
                    f"{raw_value!r} — skipped."
                )
                continue

            cell_ref = f"{get_column_letter(col)}{row}"
            result.rows.append(
                ParsedSnapshotRow(
                    account_mapping=mapping,
                    snapshot_date=snapshot_date,
                    value=value,
                    cell=cell_ref,
                )
            )

    return result
