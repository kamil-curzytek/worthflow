import datetime as dt
from decimal import Decimal

from app.database.models import AccountType, AssetClass
from app.domain.accounts.schemas import AccountCreate
from app.services import accounts_service, snapshots_service
from app.services.calculations import portfolio as calc


def make_account(db, user, name, currency, asset_class=AssetClass.CASH):
    payload = AccountCreate(
        name=name, type=AccountType.CHECKING, asset_class=asset_class, currency=currency
    )
    return accounts_service.create_account(db, user.id, payload)


def snap(db, account, date, value):
    return snapshots_service.create_snapshot(
        db, account=account, snapshot_date=date, value=Decimal(value)
    )


def test_portfolio_value_converts_multi_currency_accounts(db, user, fx):
    eur_account = make_account(db, user, "EUR acct", "EUR")
    pln_account = make_account(db, user, "PLN acct", "PLN")
    snap(db, eur_account, dt.date(2024, 1, 1), "1000")
    snap(db, pln_account, dt.date(2024, 1, 1), "1000")

    total = calc.portfolio_value_as_of(db, fx, "EUR", dt.date(2024, 1, 15))
    # 1000 EUR + 1000 PLN * 0.23 (fake rate) = 1230
    assert total == Decimal("1230.00")


def test_portfolio_value_as_of_uses_latest_snapshot_at_or_before(db, user, fx):
    account = make_account(db, user, "Acct", "EUR")
    snap(db, account, dt.date(2024, 1, 1), "1000")
    snap(db, account, dt.date(2024, 3, 1), "1500")

    # Between Jan and Mar, should still show the January value (carry-forward).
    value = calc.portfolio_value_as_of(db, fx, "EUR", dt.date(2024, 2, 1))
    assert value == Decimal(1000)


def test_missing_data_before_account_existed_is_excluded_not_zero(db, user, fx):
    account = make_account(db, user, "New account", "EUR")
    snap(db, account, dt.date(2024, 6, 1), "500")

    # Before the account's first snapshot, it should contribute nothing (not
    # be counted as a zero balance dragging down history that predates it).
    value = calc.portfolio_value_as_of(db, fx, "EUR", dt.date(2024, 1, 1))
    assert value == Decimal(0)


def test_deactivated_account_still_counts_in_portfolio_value_as_of(db, user, fx):
    # as_of is a point-in-time historical query; deactivation is a present-day
    # event and shouldn't rewrite history from before it happened.
    account = make_account(db, user, "Closed account", "EUR")
    snap(db, account, dt.date(2024, 1, 1), "500")
    accounts_service.deactivate_account(db, account.id)  # deactivated "now" (test run time)

    value = calc.portfolio_value_as_of(db, fx, "EUR", dt.date(2024, 1, 15))
    assert value == Decimal(500)


def test_deactivated_account_stops_counting_after_its_deactivation_date(db, user, fx):
    # The actual bug this guards against: a deactivated account's last known
    # balance must NOT carry forward indefinitely into months after it was
    # closed — only up through its own deactivation date.
    account = make_account(db, user, "Closed account", "EUR")
    snap(db, account, dt.date(2024, 1, 1), "500")
    accounts_service.deactivate_account(db, account.id)
    account.deactivated_at = dt.datetime(2024, 2, 15, tzinfo=dt.timezone.utc)
    db.commit()

    # Before/at the deactivation date: still counts (history is untouched).
    assert calc.portfolio_value_as_of(db, fx, "EUR", dt.date(2024, 2, 15)) == Decimal(500)
    # After it: no longer counts, instead of freezing 500 forever.
    assert calc.portfolio_value_as_of(db, fx, "EUR", dt.date(2024, 6, 1)) == Decimal(0)


def test_asset_class_trend_drops_a_class_once_its_only_account_is_deactivated(db, user, fx):
    # asset_class_trend answers "what do I hold today, broken down by class" —
    # a class with no active accounts left drops out entirely, even for the
    # months it genuinely had value in, unlike portfolio_trend's whole-history
    # total. The two are allowed to disagree for exactly this reason.
    account = make_account(db, user, "Wallet", "EUR", AssetClass.CRYPTO)
    snap(db, account, dt.date(2024, 1, 1), "1000")
    accounts_service.deactivate_account(db, account.id)
    account.deactivated_at = dt.datetime(2024, 1, 31, tzinfo=dt.timezone.utc)
    db.commit()

    start, end = dt.date(2024, 1, 1), dt.date(2024, 3, 31)
    _months, series = calc.asset_class_trend(db, fx, "EUR", start=start, end=end)
    trend = calc.portfolio_trend(db, fx, "EUR", start=start, end=end)

    assert series == []
    # Meanwhile the whole-portfolio total still reflects January's real value.
    assert [p.value for p in trend] == [Decimal(1000), Decimal(0), Decimal(0)]


def test_asset_class_trend_keeps_class_with_another_active_account(db, user, fx):
    closed = make_account(db, user, "Old wallet", "EUR", AssetClass.CRYPTO)
    still_active = make_account(db, user, "New wallet", "EUR", AssetClass.CRYPTO)
    snap(db, closed, dt.date(2024, 1, 1), "1000")
    snap(db, still_active, dt.date(2024, 1, 1), "500")
    accounts_service.deactivate_account(db, closed.id)

    _months, series = calc.asset_class_trend(db, fx, "EUR")
    by_class = {s.asset_class: s.values for s in series}
    assert by_class["crypto"] == [Decimal(1500)]


def test_portfolio_trend_empty_when_no_data(db, fx):
    assert calc.portfolio_trend(db, fx, "EUR") == []


def test_portfolio_trend_one_point_per_month_end(db, user, fx):
    account = make_account(db, user, "Acct", "EUR")
    snap(db, account, dt.date(2024, 1, 5), "1000")
    snap(db, account, dt.date(2024, 2, 10), "1100")
    snap(db, account, dt.date(2024, 3, 20), "1300")

    trend = calc.portfolio_trend(db, fx, "EUR")
    assert [p.date for p in trend] == [
        dt.date(2024, 1, 31),
        dt.date(2024, 2, 29),  # 2024 is a leap year
        dt.date(2024, 3, 31),
    ]
    assert [p.value for p in trend] == [Decimal(1000), Decimal(1100), Decimal(1300)]


def test_portfolio_trend_handles_missing_month_with_carry_forward(db, user, fx):
    account = make_account(db, user, "Acct", "EUR")
    snap(db, account, dt.date(2024, 1, 1), "1000")
    # No February update.
    snap(db, account, dt.date(2024, 3, 1), "1200")

    trend = calc.portfolio_trend(db, fx, "EUR")
    values = {p.date: p.value for p in trend}
    assert values[dt.date(2024, 2, 29)] == Decimal(1000)  # carried forward from January
    assert values[dt.date(2024, 3, 31)] == Decimal(1200)


def test_account_trend_for_single_account(db, user, fx):
    account = make_account(db, user, "Acct", "PLN")
    snap(db, account, dt.date(2024, 1, 1), "1000")
    snap(db, account, dt.date(2024, 2, 1), "2000")

    trend = calc.account_trend(db, fx, account, "EUR")
    assert trend[0].value == Decimal("230.00")  # 1000 * 0.23
    assert trend[1].value == Decimal("460.00")  # 2000 * 0.23


def test_accounts_monthly_table_native_currency_no_conversion(db, user):
    eur_account = make_account(db, user, "EUR acct", "EUR")
    pln_account = make_account(db, user, "PLN acct", "PLN")
    snap(db, eur_account, dt.date(2024, 1, 1), "1000")
    snap(db, eur_account, dt.date(2024, 2, 1), "1100")
    snap(db, pln_account, dt.date(2024, 2, 1), "5000")

    months, rows = calc.accounts_monthly_table(db)

    assert months == [dt.date(2024, 1, 31), dt.date(2024, 2, 29)]
    by_name = {r.account_name: r for r in rows}
    assert by_name["EUR acct"].currency == "EUR"
    assert by_name["EUR acct"].values == [Decimal(1000), Decimal(1100)]
    # PLN account didn't exist in January — None, not a fabricated zero.
    assert by_name["PLN acct"].values == [None, Decimal(5000)]


def test_accounts_monthly_table_excludes_inactive_by_default(db, user):
    account = make_account(db, user, "Acct", "EUR")
    snap(db, account, dt.date(2024, 1, 1), "1000")
    accounts_service.deactivate_account(db, account.id)

    _, rows = calc.accounts_monthly_table(db)
    assert rows == []

    _, rows = calc.accounts_monthly_table(db, include_inactive=True)
    assert len(rows) == 1


def test_accounts_monthly_table_empty_when_no_data(db):
    months, rows = calc.accounts_monthly_table(db)
    assert months == []
    assert rows == []


def test_allocation_by_asset_class(db, user, fx):
    cash = make_account(db, user, "Cash acct", "EUR", AssetClass.CASH)
    crypto = make_account(db, user, "Crypto acct", "EUR", AssetClass.CRYPTO)
    snap(db, cash, dt.date(2024, 1, 1), "800")
    snap(db, crypto, dt.date(2024, 1, 1), "200")

    slices = calc.allocation_by_asset_class(db, fx, "EUR", dt.date(2024, 1, 15))
    by_label = {s.label: s for s in slices}
    assert by_label["cash"].value == Decimal(800)
    assert by_label["cash"].percentage == Decimal(80)
    assert by_label["crypto"].percentage == Decimal(20)


def test_asset_class_trend_sums_to_portfolio_trend_each_month(db, user, fx):
    cash_eur = make_account(db, user, "Cash EUR", "EUR", AssetClass.CASH)
    cash_pln = make_account(db, user, "Cash PLN", "PLN", AssetClass.CASH)
    trading = make_account(db, user, "Broker", "PLN", AssetClass.TRADING)
    crypto = make_account(db, user, "Wallet", "EUR", AssetClass.CRYPTO)
    snap(db, cash_eur, dt.date(2024, 1, 5), "1000")
    snap(db, cash_pln, dt.date(2024, 1, 5), "2000")
    snap(db, trading, dt.date(2024, 2, 10), "10000")  # appears in month 2
    snap(db, cash_eur, dt.date(2024, 3, 1), "1500")
    snap(db, crypto, dt.date(2024, 3, 15), "0")  # zero everywhere -> left out
    # cash_eur is still active, so the "cash" class stays visible and keeps
    # summing to the portfolio total even though one of its accounts closed.
    accounts_service.deactivate_account(db, cash_pln.id)

    months, series = calc.asset_class_trend(db, fx, "EUR")
    trend = calc.portfolio_trend(db, fx, "EUR")

    assert months == [p.date for p in trend]
    for i, point in enumerate(trend):
        assert sum((s.values[i] for s in series), Decimal(0)) == point.value

    by_class = {s.asset_class: s.values for s in series}
    assert set(by_class) == {"cash", "trading"}
    # Trading didn't exist in January: explicit zero, not a gap.
    assert by_class["trading"] == [Decimal(0), Decimal("2300.00"), Decimal("2300.00")]
    assert by_class["cash"] == [Decimal("1460.00"), Decimal("1460.00"), Decimal("1960.00")]
    # Ordered by latest-month value, largest first.
    assert [s.asset_class for s in series] == ["trading", "cash"]


def test_asset_class_trend_empty_when_no_data(db, fx):
    assert calc.asset_class_trend(db, fx, "EUR") == ([], [])


def test_allocation_with_no_data_returns_empty(db, fx):
    assert calc.allocation_by_asset_class(db, fx, "EUR", dt.date(2024, 1, 1)) == []


def test_account_contributions_sum_to_the_whole_portfolio_change(db, user, fx):
    eur_account = make_account(db, user, "EUR acct", "EUR")
    pln_account = make_account(db, user, "PLN acct", "PLN")
    snap(db, eur_account, dt.date(2024, 1, 1), "1000")
    snap(db, pln_account, dt.date(2024, 1, 1), "1000")
    snap(db, eur_account, dt.date(2024, 2, 1), "1200")  # +200 EUR
    snap(db, pln_account, dt.date(2024, 2, 1), "2000")  # +1000 PLN = +230 EUR

    rows = calc.account_contributions_by_month(db, fx, "EUR")
    trend = calc.portfolio_trend(db, fx, "EUR")

    assert [r.date for r in rows] == [dt.date(2024, 2, 29)]
    feb = rows[0]
    total_delta = sum((c.delta for c in feb.contributions), Decimal(0))
    expected_delta = trend[1].value - trend[0].value
    assert total_delta == expected_delta == Decimal(430)

    by_account = {c.account_name: c.delta for c in feb.contributions}
    assert by_account["EUR acct"] == Decimal(200)
    assert by_account["PLN acct"] == Decimal("230.00")


def test_account_contributions_first_appearance_counts_as_full_delta(db, user, fx):
    existing = make_account(db, user, "Existing", "EUR")
    snap(db, existing, dt.date(2024, 1, 1), "1000")
    snap(db, existing, dt.date(2024, 2, 1), "1000")  # unchanged

    new_account = make_account(db, user, "New account", "EUR")
    snap(db, new_account, dt.date(2024, 2, 1), "500")  # first-ever snapshot, in month 2

    rows = calc.account_contributions_by_month(db, fx, "EUR")
    assert len(rows) == 1
    by_account = {c.account_name: c.delta for c in rows[0].contributions}
    # Unchanged account contributes nothing (delta == 0 entries are omitted).
    assert "Existing" not in by_account
    # New account's first balance counts as its full value, not a skip.
    assert by_account["New account"] == Decimal(500)


def test_account_contributions_empty_with_fewer_than_two_months(db, user, fx):
    account = make_account(db, user, "Acct", "EUR")
    snap(db, account, dt.date(2024, 1, 1), "1000")
    assert calc.account_contributions_by_month(db, fx, "EUR") == []
