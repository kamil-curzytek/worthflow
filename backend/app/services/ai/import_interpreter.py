"""AI-assisted import: provider abstraction.

Mirrors app/services/exchange_rates/provider.py's shape — a small ABC so the
concrete AI backend (Anthropic today, others later) is swappable, and so
tests can substitute a fake provider instead of calling a real API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.services.ai.import_types import ImportInterpretation


class ImportInterpreterError(Exception):
    """The provider could not be reached, or returned something unusable."""


class ImportInterpreterProvider(ABC):
    name: str

    @abstractmethod
    def interpret(self, file_text: str) -> ImportInterpretation:
        """Propose an account/snapshot structure for the given file content.

        Raises ImportInterpreterError on failure. Never writes to the database.
        """
        raise NotImplementedError
