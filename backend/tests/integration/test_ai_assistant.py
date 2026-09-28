import datetime as dt
from decimal import Decimal

import pytest

from app.config import Settings
from app.database.models import AssetClass
from app.domain.accounts.schemas import AccountCreate
from app.services import accounts_service, snapshots_service
from app.services.ai.anthropic_assistant_provider import AnthropicAssistantProvider
from app.services.ai.assistant_provider import AssistantMessage
from app.services.ai_assistant.service import (
    AiAssistantNotConfiguredError,
    build_assistant_provider,
    build_portfolio_snapshot_text,
    chat,
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
        with pytest.raises(AiAssistantNotConfiguredError):
            build_assistant_provider(make_settings())

    def test_enabled_but_no_external_data_consent_raises(self):
        with pytest.raises(AiAssistantNotConfiguredError):
            build_assistant_provider(make_settings(ai_analysis_enabled=True))

    def test_consent_given_but_no_api_key_raises(self):
        with pytest.raises(AiAssistantNotConfiguredError):
            build_assistant_provider(
                make_settings(
                    ai_analysis_enabled=True, ai_allow_external_data=True, ai_provider="anthropic"
                )
            )

    def test_unsupported_provider_raises(self):
        with pytest.raises(AiAssistantNotConfiguredError):
            build_assistant_provider(
                make_settings(
                    ai_analysis_enabled=True, ai_allow_external_data=True, ai_provider="openai"
                )
            )

    def test_fully_configured_returns_anthropic_provider(self):
        provider = build_assistant_provider(
            make_settings(
                ai_analysis_enabled=True,
                ai_allow_external_data=True,
                ai_provider="anthropic",
                anthropic_api_key="sk-test",
            )
        )
        assert isinstance(provider, AnthropicAssistantProvider)


def test_chat_raises_when_not_configured(db, fx):
    with pytest.raises(AiAssistantNotConfiguredError):
        chat(
            db,
            fx,
            make_settings(),
            target_currency="EUR",
            goal="Long-term investing",
            messages=[AssistantMessage(role="user", content="hi")],
        )


def test_chat_rejects_empty_or_non_user_terminated_messages(db, fx):
    with pytest.raises(ValueError):
        chat(db, fx, make_settings(), target_currency="EUR", goal="", messages=[])
    with pytest.raises(ValueError):
        chat(
            db,
            fx,
            make_settings(),
            target_currency="EUR",
            goal="",
            messages=[AssistantMessage(role="assistant", content="hi")],
        )


def test_snapshot_text_includes_total_allocation_and_accounts(db, user, fx):
    cash = accounts_service.create_account(
        db,
        user.id,
        AccountCreate(
            name="Checking", type="checking", asset_class=AssetClass.CASH, currency="EUR"
        ),
    )
    snapshots_service.create_snapshot(
        db, account=cash, snapshot_date=dt.date.today(), value=Decimal(1000)
    )

    text = build_portfolio_snapshot_text(db, fx, "EUR")

    assert "Total wealth: 1000" in text
    assert "Allocation by asset class:" in text
    assert "cash: 1000" in text
    assert "Accounts:" in text
    assert "Checking (checking, cash): 1000" in text


def test_snapshot_text_handles_no_accounts(db, fx):
    text = build_portfolio_snapshot_text(db, fx, "EUR")
    assert "Total wealth: 0" in text
    assert "No accounts recorded yet." in text


def test_snapshot_text_excludes_inactive_accounts_from_account_list(db, user, fx):
    account = accounts_service.create_account(
        db,
        user.id,
        AccountCreate(name="Closed", type="checking", asset_class=AssetClass.CASH, currency="EUR"),
    )
    snapshots_service.create_snapshot(
        db, account=account, snapshot_date=dt.date.today(), value=Decimal(500)
    )
    accounts_service.deactivate_account(db, account.id)

    text = build_portfolio_snapshot_text(db, fx, "EUR")
    assert "Closed" not in text
