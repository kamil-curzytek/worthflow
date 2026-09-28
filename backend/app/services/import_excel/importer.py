"""Preview-then-commit Excel import.

preview_import never writes to the database. commit_import re-parses and
writes everything inside one ImportBatch, so a failed import is easy to spot
and every successful one is traceable back to its source file.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.database.models import Account, ImportBatch, ImportStatus, SnapshotSource
from app.services.accounts_service import (
    get_account_by_name,
    get_or_create_account,
    list_accounts,
)
from app.services.import_excel.parser import ParsedSnapshotRow, parse_raw_data_sheet
from app.services.snapshots_service import create_snapshot, find_snapshot


@dataclass
class ImportPreviewRow:
    account_name: str
    snapshot_date: str
    value: str
    currency: str
    is_new_account: bool
    is_duplicate: bool
    cell: str


@dataclass
class ImportPreview:
    rows: list[ImportPreviewRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def new_snapshot_count(self) -> int:
        return sum(1 for r in self.rows if not r.is_duplicate)

    @property
    def duplicate_count(self) -> int:
        return sum(1 for r in self.rows if r.is_duplicate)

    @property
    def new_account_names(self) -> list[str]:
        seen = []
        for r in self.rows:
            if r.is_new_account and r.account_name not in seen:
                seen.append(r.account_name)
        return seen


def _existing_account_names(db: Session, user_id: str) -> set[str]:
    return {a.name for a in list_accounts(db, include_inactive=True) if a.user_id == user_id}


def preview_import(db: Session, user_id: str, file_path: str) -> ImportPreview:
    parsed = parse_raw_data_sheet(file_path)
    preview = ImportPreview(warnings=list(parsed.warnings))

    known_account_names = _existing_account_names(db, user_id)
    accounts_seen_in_file: set[str] = set()

    for row in parsed.rows:
        account_name = row.account_mapping.account_name
        is_new_account = (
            account_name not in known_account_names and account_name not in accounts_seen_in_file
        )
        accounts_seen_in_file.add(account_name)

        preview.rows.append(
            ImportPreviewRow(
                account_name=account_name,
                snapshot_date=row.snapshot_date.isoformat(),
                value=str(row.value),
                currency=row.account_mapping.currency,
                is_new_account=is_new_account,
                is_duplicate=False,
                cell=row.cell,
            )
        )

    _mark_duplicates(db, user_id, preview)
    return preview


def _mark_duplicates(db: Session, user_id: str, preview: ImportPreview) -> None:
    account_cache: dict[str, Account | None] = {}
    for row in preview.rows:
        account = account_cache.get(row.account_name)
        if account is None:
            account = get_account_by_name(db, user_id, row.account_name)
            account_cache[row.account_name] = account
        if account is None:
            continue  # new account — can't already have a snapshot
        existing = find_snapshot(db, account.id, dt.date.fromisoformat(row.snapshot_date))
        row.is_duplicate = existing is not None


def commit_import(
    db: Session, user_id: str, file_path: str, *, overwrite_duplicates: bool = False
) -> ImportBatch:
    parsed = parse_raw_data_sheet(file_path)

    batch = ImportBatch(source_filename=file_path, status=ImportStatus.PENDING, row_count=0)
    db.add(batch)
    db.commit()
    db.refresh(batch)

    account_cache: dict[str, Account] = {}
    written = 0
    try:
        for row in parsed.rows:
            account = _resolve_account(db, user_id, row, account_cache)
            existing = find_snapshot(db, account.id, row.snapshot_date)
            if existing is not None and not overwrite_duplicates:
                continue
            _write_snapshot(db, account, row, batch.id, overwrite_duplicates)
            written += 1

        batch.row_count = written
        batch.status = ImportStatus.COMMITTED
        if parsed.warnings:
            batch.notes = "\n".join(parsed.warnings)[:2000]
        db.commit()
    except Exception:
        batch.status = ImportStatus.FAILED
        db.commit()
        raise

    db.refresh(batch)
    return batch


def _resolve_account(
    db: Session, user_id: str, row: ParsedSnapshotRow, cache: dict[str, Account]
) -> Account:
    m = row.account_mapping
    if m.account_name not in cache:
        cache[m.account_name] = get_or_create_account(
            db,
            user_id,
            name=m.account_name,
            type=m.account_type,
            asset_class=m.asset_class,
            currency=m.currency,
        )
    return cache[m.account_name]


def _write_snapshot(
    db: Session, account: Account, row: ParsedSnapshotRow, batch_id: str, overwrite: bool
) -> None:
    create_snapshot(
        db,
        account=account,
        snapshot_date=row.snapshot_date,
        value=row.value,
        source=SnapshotSource.IMPORT_EXCEL,
        import_batch_id=batch_id,
        allow_overwrite=overwrite,
    )
