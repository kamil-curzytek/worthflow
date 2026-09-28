import datetime as dt
from decimal import Decimal

import pytest

from app.database.models import AccountType, AssetClass
from app.domain.accounts.schemas import AccountCreate
from app.services import accounts_service, snapshots_service


def make_account(db, user, name="Test Savings", currency="EUR"):
    return accounts_service.create_account(
        db,
        user.id,
        AccountCreate(
            name=name, type=AccountType.SAVINGS, asset_class=AssetClass.CASH, currency=currency
        ),
    )


def test_create_and_list_accounts(db, user):
    make_account(db, user)
    accounts = accounts_service.list_accounts(db)
    assert len(accounts) == 1
    assert accounts[0].name == "Test Savings"


def test_duplicate_account_name_rejected(db, user):
    make_account(db, user)
    with pytest.raises(accounts_service.DuplicateAccountError):
        make_account(db, user)


def test_deactivate_account_excluded_from_default_listing(db, user):
    account = make_account(db, user)
    accounts_service.deactivate_account(db, account.id)
    assert accounts_service.list_accounts(db) == []
    assert len(accounts_service.list_accounts(db, include_inactive=True)) == 1


def test_get_or_create_account_is_idempotent(db, user):
    kwargs = dict(
        name="N26", type=AccountType.CHECKING, asset_class=AssetClass.CASH, currency="EUR"
    )
    first = accounts_service.get_or_create_account(db, user.id, **kwargs)
    second = accounts_service.get_or_create_account(db, user.id, **kwargs)
    assert first.id == second.id


def test_create_snapshot_and_duplicate_rejected(db, user):
    account = make_account(db, user)
    snapshots_service.create_snapshot(
        db, account=account, snapshot_date=dt.date(2024, 1, 1), value=Decimal(1000)
    )
    with pytest.raises(snapshots_service.DuplicateSnapshotError):
        snapshots_service.create_snapshot(
            db, account=account, snapshot_date=dt.date(2024, 1, 1), value=Decimal(2000)
        )


def test_add_or_update_monthly_snapshot_overwrites_same_date_only(db, user):
    account = make_account(db, user)
    snapshots_service.add_or_update_monthly_snapshot(
        db, account=account, snapshot_date=dt.date(2024, 1, 1), value=Decimal(1000)
    )
    snapshots_service.create_snapshot(
        db, account=account, snapshot_date=dt.date(2024, 2, 1), value=Decimal(1100)
    )

    corrected = snapshots_service.add_or_update_monthly_snapshot(
        db, account=account, snapshot_date=dt.date(2024, 1, 1), value=Decimal(999)
    )
    assert corrected.value == Decimal(999)

    # February must be untouched by correcting January.
    feb = snapshots_service.find_snapshot(db, account.id, dt.date(2024, 2, 1))
    assert feb.value == Decimal(1100)


def test_snapshot_stores_account_currency(db, user):
    account = make_account(db, user, currency="PLN")
    snapshot = snapshots_service.create_snapshot(
        db, account=account, snapshot_date=dt.date(2024, 1, 1), value=Decimal(500)
    )
    assert snapshot.currency == "PLN"


def test_update_snapshot_corrects_value_and_note(db, user):
    account = make_account(db, user)
    snapshot = snapshots_service.create_snapshot(
        db, account=account, snapshot_date=dt.date(2024, 1, 1), value=Decimal(1000)
    )
    updated = snapshots_service.update_snapshot(
        db, snapshot.id, value=Decimal(1050), note="fixed typo"
    )
    assert updated.value == Decimal(1050)
    assert updated.note == "fixed typo"


def test_delete_snapshot(db, user):
    account = make_account(db, user)
    snapshot = snapshots_service.create_snapshot(
        db, account=account, snapshot_date=dt.date(2024, 1, 1), value=Decimal(1000)
    )
    snapshots_service.delete_snapshot(db, snapshot.id)
    with pytest.raises(snapshots_service.SnapshotNotFoundError):
        snapshots_service.get_snapshot(db, snapshot.id)


def test_latest_snapshot_per_account(db, user):
    account = make_account(db, user)
    snapshots_service.create_snapshot(
        db, account=account, snapshot_date=dt.date(2024, 1, 1), value=Decimal(1000)
    )
    snapshots_service.create_snapshot(
        db, account=account, snapshot_date=dt.date(2024, 3, 1), value=Decimal(1200)
    )
    latest = snapshots_service.latest_snapshot_per_account(db, account.id)
    assert latest.snapshot_date == dt.date(2024, 3, 1)


def test_set_monthly_value_creates_when_month_empty(db, user):
    account = make_account(db, user)
    snapshot = snapshots_service.set_monthly_value(
        db, account=account, year=2024, month=3, value=Decimal(1500)
    )
    assert snapshot.snapshot_date == dt.date(2024, 3, 31)  # last day of the month
    assert snapshot.value == Decimal(1500)


def test_set_monthly_value_corrects_existing_snapshot_in_place(db, user):
    account = make_account(db, user)
    # Simulates an Excel import, which lands on the 1st of the month.
    original = snapshots_service.create_snapshot(
        db, account=account, snapshot_date=dt.date(2024, 3, 1), value=Decimal(1000)
    )

    corrected = snapshots_service.set_monthly_value(
        db, account=account, year=2024, month=3, value=Decimal(1234)
    )

    assert corrected.id == original.id  # same row corrected, not a duplicate
    assert corrected.snapshot_date == dt.date(2024, 3, 1)  # original date preserved
    assert corrected.value == Decimal(1234)

    all_march_snapshots = [
        s
        for s in snapshots_service.list_snapshots(db, account_id=account.id)
        if s.snapshot_date.month == 3
    ]
    assert len(all_march_snapshots) == 1


def test_set_monthly_value_does_not_touch_other_months(db, user):
    account = make_account(db, user)
    snapshots_service.create_snapshot(
        db, account=account, snapshot_date=dt.date(2024, 2, 1), value=Decimal(500)
    )
    snapshots_service.set_monthly_value(db, account=account, year=2024, month=3, value=Decimal(999))

    february = snapshots_service.find_snapshot(db, account.id, dt.date(2024, 2, 1))
    assert february.value == Decimal(500)
