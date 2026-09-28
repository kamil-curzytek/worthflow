"""SQLAlchemy ORM models — the normalized, long-term data model.

This is intentionally NOT a mirror of the source Excel file. The Excel sheet is
a wide, one-row-per-account / one-column-per-month layout; here every balance
observation is its own row (a Snapshot), which is what lets us preserve full
history, add accounts freely, and query trends without reshaping data.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class AccountType(str, enum.Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    BROKERAGE = "brokerage"
    CASH = "cash"
    CRYPTO = "crypto"
    PENSION = "pension"
    EQUITY_COMPENSATION = "equity_compensation"
    OTHER = "other"


class AssetClass(str, enum.Enum):
    """Cross-cutting classification used for allocation breakdowns.

    Mirrors the CASH / TRADING / CRYPTO / equity rollups the source Excel
    computed by hand per account.
    """

    CASH = "cash"
    TRADING = "trading"
    CRYPTO = "crypto"
    EQUITY_COMPENSATION = "equity_compensation"
    OTHER = "other"


class SnapshotSource(str, enum.Enum):
    MANUAL = "manual"
    IMPORT_EXCEL = "import_excel"
    CLI = "cli"


class ImportStatus(str, enum.Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    accounts: Mapped[list[Account]] = relationship(back_populates="user")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_account_user_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[AccountType] = mapped_column(String(32))
    asset_class: Mapped[AssetClass] = mapped_column(String(32))
    institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    user: Mapped[User] = relationship(back_populates="accounts")
    snapshots: Mapped[list[Snapshot]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class Snapshot(Base):
    """A dated balance observation for one account. The core historical record.

    Snapshots are never overwritten to record a *different* date — each month
    adds a new row. An existing snapshot may be corrected in place (e.g. a
    typo), which is a distinct operation from adding a new month's value.
    """

    __tablename__ = "snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "snapshot_date", name="uq_snapshot_account_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    snapshot_date: Mapped[dt.date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    source: Mapped[SnapshotSource] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    import_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("import_batches.id"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    account: Mapped[Account] = relationship(back_populates="snapshots")


class ExchangeRate(Base):
    """A historically-reproducible FX rate: which rate was used is always known."""

    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint(
            "base_currency", "quote_currency", "rate_date", "source", name="uq_rate_lookup"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    base_currency: Mapped[str] = mapped_column(String(3))
    quote_currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    rate_date: Mapped[dt.date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SubLedgerEntry(Base):
    """A dated metric observation outside the account/snapshot model.

    Mirrors Snapshot's shape (one row per observation, correct-in-place via
    the same find-in-month-or-create pattern) but for sub-ledger detail that
    isn't itself an account balance — e.g. Trading212's monthly dividends,
    ESPP's share counts, Passive income's per-source interest. `category`
    groups rows by tab (e.g. "trading212"), `metric` identifies which row
    within that tab (e.g. "dividends_monthly") — see
    app/services/sub_ledger/metrics.py for the defined categories/metrics.
    """

    __tablename__ = "sub_ledger_entries"
    __table_args__ = (
        UniqueConstraint("category", "metric", "entry_date", name="uq_sub_ledger_entry"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    category: Mapped[str] = mapped_column(String(32))
    metric: Mapped[str] = mapped_column(String(64))
    entry_date: Mapped[dt.date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ImportBatch(Base):
    """Tracks a single import run for traceability and duplicate detection."""

    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_filename: Mapped[str] = mapped_column(String(500))
    status: Mapped[ImportStatus] = mapped_column(String(32), default=ImportStatus.PENDING)
    row_count: Mapped[int] = mapped_column(default=0)
    imported_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
