"""AI Assistant: gating, portfolio-snapshot building, and chat orchestration.

Mirrors app/services/import_ai/service.py's gating shape. The AI never
computes anything here either — build_portfolio_snapshot_text assembles a
plain-text summary purely from app/services/calculations/ output, and that
text (plus the conversation) is the only thing handed to the provider.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.config import Settings
from app.services import accounts_service
from app.services.ai.anthropic_assistant_provider import AnthropicAssistantProvider
from app.services.ai.assistant_provider import AssistantMessage, PortfolioAssistantProvider
from app.services.calculations import portfolio as calc
from app.services.exchange_rates.service import ExchangeRateService

RECENT_TREND_MONTHS = 12


def _enum_value(x: object) -> str:
    return x.value if hasattr(x, "value") else str(x)


class AiAssistantNotConfiguredError(Exception):
    """The AI Assistant isn't usable with the current configuration."""


def build_assistant_provider(settings: Settings) -> PortfolioAssistantProvider:
    if not settings.ai_analysis_enabled or not settings.ai_allow_external_data:
        raise AiAssistantNotConfiguredError(
            "The AI Assistant is off. It sends a summary of your portfolio to an external AI "
            "provider, so it requires both AI_ANALYSIS_ENABLED=true and "
            "AI_ALLOW_EXTERNAL_DATA=true in your .env — see the README."
        )
    if settings.ai_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise AiAssistantNotConfiguredError("ANTHROPIC_API_KEY is not set in your .env.")
        return AnthropicAssistantProvider(
            api_key=settings.anthropic_api_key, model=settings.ai_model
        )
    raise AiAssistantNotConfiguredError(
        f"AI provider {settings.ai_provider!r} does not support the AI Assistant yet."
    )


def build_portfolio_snapshot_text(
    db: Session, fx: ExchangeRateService, target_currency: str
) -> str:
    """A compact, deterministic, plain-text description of the current
    portfolio — the only financial context the AI ever receives."""
    today = dt.date.today()
    total = calc.portfolio_value_as_of(db, fx, target_currency, today)
    trend = calc.portfolio_trend(db, fx, target_currency)
    allocation = calc.allocation_by_asset_class(db, fx, target_currency, today)
    accounts = accounts_service.list_accounts(db, include_inactive=False)

    lines = [f"Total wealth: {total} {target_currency} (as of {today.isoformat()})"]

    recent = trend[-RECENT_TREND_MONTHS:] if len(trend) > 1 else trend
    if len(recent) >= 2:
        first, last = recent[0], recent[-1]
        change = last.value - first.value
        pct = (change / first.value * 100) if first.value else None
        pct_text = f" ({pct:+.1f}%)" if pct is not None else ""
        lines.append(
            f"Change from {first.date.isoformat()} to {last.date.isoformat()}: "
            f"{change:+.2f} {target_currency}{pct_text}"
        )

    if allocation:
        lines.append("Allocation by asset class:")
        for s in sorted(allocation, key=lambda s: s.value, reverse=True):
            lines.append(f"  - {s.label}: {s.value} {target_currency} ({s.percentage:.1f}%)")

    if accounts:
        lines.append("Accounts:")
        for account in accounts:
            balance = calc.account_balance_as_of(db, account, today)
            if balance is None:
                value_text = "no data yet"
            else:
                value_text = f"{balance.value} {balance.currency}"
            type_text = _enum_value(account.type)
            asset_class_text = _enum_value(account.asset_class)
            lines.append(f"  - {account.name} ({type_text}, {asset_class_text}): {value_text}")

    if len(accounts) == 0:
        lines.append("No accounts recorded yet.")

    return "\n".join(lines)


def chat(
    db: Session,
    fx: ExchangeRateService,
    settings: Settings,
    *,
    target_currency: str,
    goal: str,
    messages: list[AssistantMessage],
) -> str:
    if not messages or messages[-1].role != "user":
        raise ValueError("messages must be non-empty and end with a user turn")

    provider = build_assistant_provider(settings)
    snapshot = build_portfolio_snapshot_text(db, fx, target_currency)
    return provider.reply(portfolio_summary=snapshot, goal=goal, messages=messages)
