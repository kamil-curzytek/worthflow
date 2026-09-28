"""Anthropic-backed PortfolioAssistantProvider.

Uses the Messages API directly over httpx (no SDK dependency), same as
anthropic_import_interpreter.py. Unlike the import interpreter, this is a
free-form multi-turn chat — no JSON parsing, the model's text is returned as-is.
"""

from __future__ import annotations

import httpx

from app.net import ensure_system_trust_store
from app.services.ai.assistant_provider import (
    AssistantMessage,
    AssistantProviderError,
    PortfolioAssistantProvider,
)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MAX_REPLY_TOKENS = 1024

SYSTEM_PROMPT_TEMPLATE = """You are the AI Assistant inside Worthflow, a personal, local-first \
net-worth dashboard. You are talking directly with the one person who owns this data — there \
are no other users and nothing you say is shown to anyone else.

You have been given a deterministic snapshot of their current portfolio below, computed by the \
app itself — not by you. Use ONLY these numbers; never invent an account or balance, and never \
recompute or "correct" a figure in the snapshot — describe and reason about it qualitatively.

Ground rules:
- You have no access to live prices, interest rates, or market data, and your knowledge has a \
training cutoff — never state a specific current price, yield, or rate as fact. When you name an \
instrument or account type (e.g. "a broad global equity index fund" or "a high-yield \
instant-access savings account"), speak only in general, named categories — never a specific \
ticker's current price or a specific bank's current rate — and explicitly tell the user to verify \
current terms themselves before acting on anything.
- You are not a licensed financial advisor. Say so plainly if the user seems to be treating your \
suggestions as guaranteed or personalized advice rather than general, educational information.
- If their goal, risk tolerance, or time horizon isn't clear yet, ask one short clarifying \
question before jumping to specific suggestions — but don't stall if they've already told you \
enough or ask you to just proceed.
- Keep replies concise. This is a chat, not a report.

Portfolio snapshot:
{snapshot}

Stated goal: {goal}
"""


class AnthropicAssistantProvider(PortfolioAssistantProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: float = 60.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def reply(
        self, *, portfolio_summary: str, goal: str, messages: list[AssistantMessage]
    ) -> str:
        ensure_system_trust_store()
        system = SYSTEM_PROMPT_TEMPLATE.format(
            snapshot=portfolio_summary, goal=goal.strip() or "(not stated yet)"
        )
        try:
            response = httpx.post(
                API_URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": API_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": MAX_REPLY_TOKENS,
                    "system": system,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
            text = "".join(
                block.get("text", "")
                for block in data.get("content", [])
                if block.get("type") == "text"
            )
        except httpx.HTTPError as exc:
            raise AssistantProviderError(f"Could not reach the {self.name} API: {exc}") from exc

        if not text.strip():
            raise AssistantProviderError(f"The {self.name} API returned an empty reply.")
        return text.strip()
