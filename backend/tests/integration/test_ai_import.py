import datetime as dt
from decimal import Decimal

import pytest

from app.config import Settings
from app.database.models import AccountType, AssetClass
from app.domain.accounts.schemas import AccountCreate
from app.services import accounts_service, snapshots_service
from app.services.ai.anthropic_import_interpreter import AnthropicImportInterpreter
from app.services.import_ai.service import (
    AiAccountSelection,
    AiEntrySelection,
    AiImportNotConfiguredError,
    build_import_interpreter,
    commit_ai_import,
)


def make_settings(**overrides) -> Settings:
    base = {
        "ai_analysis_enabled": False,
        "ai_allow_external_data": False,
        "ai_provider": "local",
        "anthropic_api_key": "",
    }
    base.update(overrides)
    return Settings(**base)


class TestGating:
    def test_disabled_by_default_raises(self):
        with pytest.raises(AiImportNotConfiguredError):
            build_import_interpreter(make_settings())

    def test_enabled_but_no_external_data_consent_raises(self):
        with pytest.raises(AiImportNotConfiguredError):
            build_import_interpreter(make_settings(ai_analysis_enabled=True))

    def test_consent_given_but_no_api_key_raises(self):
        with pytest.raises(AiImportNotConfiguredError):
            build_import_interpreter(
                make_settings(
                    ai_analysis_enabled=True, ai_allow_external_data=True, ai_provider="anthropic"
                )
            )

    def test_unsupported_provider_raises(self):
        with pytest.raises(AiImportNotConfiguredError):
            build_import_interpreter(
                make_settings(
                    ai_analysis_enabled=True, ai_allow_external_data=True, ai_provider="openai"
                )
            )

    def test_fully_configured_returns_anthropic_provider(self):
        provider = build_import_interpreter(
            make_settings(
                ai_analysis_enabled=True,
                ai_allow_external_data=True,
                ai_provider="anthropic",
                anthropic_api_key="sk-test",
            )
        )
        assert isinstance(provider, AnthropicImportInterpreter)


def test_commit_ai_import_creates_accounts_and_snapshots(db, user):
    selections = [
        AiAccountSelection(
            name="AI Checking",
            currency="EUR",
            type=AccountType.CHECKING,
            asset_class=AssetClass.CASH,
            entries=[
                AiEntrySelection(date=dt.date(2024, 1, 1), value="1000"),
                AiEntrySelection(date=dt.date(2024, 2, 1), value="1100"),
            ],
        )
    ]
    batch = commit_ai_import(db, user.id, selections)
    assert batch.row_count == 2
    assert batch.status == "committed"

    account = accounts_service.get_account_by_name(db, user.id, "AI Checking")
    assert account is not None
    snaps = snapshots_service.list_snapshots(db, account_id=account.id)
    assert len(snaps) == 2


def test_commit_ai_import_respects_include_false_on_account(db, user):
    selections = [
        AiAccountSelection(
            name="Excluded",
            currency="EUR",
            type=AccountType.CHECKING,
            asset_class=AssetClass.CASH,
            include=False,
            entries=[AiEntrySelection(date=dt.date(2024, 1, 1), value="1000")],
        )
    ]
    batch = commit_ai_import(db, user.id, selections)
    assert batch.row_count == 0
    assert accounts_service.get_account_by_name(db, user.id, "Excluded") is None


def test_commit_ai_import_respects_include_false_on_entry(db, user):
    selections = [
        AiAccountSelection(
            name="Partial",
            currency="EUR",
            type=AccountType.CHECKING,
            asset_class=AssetClass.CASH,
            entries=[
                AiEntrySelection(date=dt.date(2024, 1, 1), value="1000", include=True),
                AiEntrySelection(date=dt.date(2024, 2, 1), value="2000", include=False),
            ],
        )
    ]
    batch = commit_ai_import(db, user.id, selections)
    assert batch.row_count == 1
    account = accounts_service.get_account_by_name(db, user.id, "Partial")
    snaps = snapshots_service.list_snapshots(db, account_id=account.id)
    assert len(snaps) == 1
    assert snaps[0].snapshot_date.month == 1  # the excluded February entry never got written
    assert snaps[0].value == Decimal(1000)


def test_commit_ai_import_corrects_existing_month_not_duplicates(db, user):
    account = accounts_service.create_account(
        db,
        user.id,
        AccountCreate(
            name="Existing", type=AccountType.CHECKING, asset_class=AssetClass.CASH, currency="EUR"
        ),
    )
    snapshots_service.create_snapshot(
        db, account=account, snapshot_date=dt.date(2024, 3, 5), value=Decimal(500)
    )

    selections = [
        AiAccountSelection(
            name="Existing",
            currency="EUR",
            type=AccountType.CHECKING,
            asset_class=AssetClass.CASH,
            entries=[AiEntrySelection(date=dt.date(2024, 3, 1), value="750")],
        )
    ]
    commit_ai_import(db, user.id, selections)

    all_snaps = snapshots_service.list_snapshots(db, account_id=account.id)
    snaps = [s for s in all_snaps if s.snapshot_date.month == 3]
    assert len(snaps) == 1
    assert snaps[0].value == Decimal(750)
