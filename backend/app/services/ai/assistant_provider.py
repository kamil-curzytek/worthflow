"""AI Assistant chat: provider abstraction.

Mirrors app/services/ai/import_interpreter.py's shape — a small ABC so the
concrete AI backend (Anthropic today, others later) is swappable, and so
tests can substitute a fake provider instead of calling a real API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class AssistantProviderError(Exception):
    """The provider could not be reached, or returned something unusable."""


@dataclass
class AssistantMessage:
    role: str  # "user" | "assistant"
    content: str


class PortfolioAssistantProvider(ABC):
    name: str

    @abstractmethod
    def reply(
        self, *, portfolio_summary: str, goal: str, messages: list[AssistantMessage]
    ) -> str:
        """Continue the conversation and return the assistant's next reply.

        portfolio_summary is a deterministic, pre-computed description of the
        user's current portfolio (never arithmetic performed by the AI
        itself). Raises AssistantProviderError on failure. Never writes to
        the database.
        """
        raise NotImplementedError
